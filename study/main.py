"""
main.py  ——  结构化感知系统统一入口

两种运行模式
------------
视觉模式（默认）  : 打开 OpenCV 窗口显示摄像头画面，检测结果叠加在视频上，
                    同时在终端打印显著事件。
终端模式          : --no-view，不打开窗口，纯终端事件流（适合无显示器服务器）。

用法
----
python main.py                          # 摄像头 + 可视化窗口
python main.py --source video.mp4       # 视频文件
python main.py --source rtsp://...      # RTSP 流
python main.py --no-view                # 纯终端，无窗口
python main.py --no-yolo                # 只跑运动检测 + 姿态
python main.py --no-pose                # 不跑姿态
python main.py --min-conf 0.5           # 终端只打印 conf≥0.5 的事件
python main.py --always-detect          # 无论有无运动都跑 YOLO/Pose

视觉模式按键
-----------
Q / ESC   退出
P         暂停 / 继续
C         清除事件日志
1         全部叠加（运动遮罩 + 检测框 + 姿态 + 日志）
2         仅检测框 + 日志
3         仅运动遮罩
S         截图保存到 snapshot_<timestamp>.jpg
"""
from __future__ import annotations
import argparse
import time
import os
from collections import defaultdict, deque

import cv2
import numpy as np

from perception import PerceptionEvent, VideoPipeline
from perception.event import VideoEventType


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  颜色表（BGR，供 OpenCV 使用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C_GREEN   = (60, 200, 80)
C_BLUE    = (220, 140, 50)
C_ORANGE  = (30, 140, 220)
C_PURPLE  = (200, 100, 180)
C_RED     = (50, 60, 220)
C_WHITE   = (240, 240, 240)
C_BLACK   = (0, 0, 0)
C_YELLOW  = (30, 220, 220)

# ANSI 颜色（终端输出）
TERM = {
    VideoEventType.MOTION_DETECTED: "\033[33m",
    VideoEventType.SCENE_CHANGE:    "\033[35m",
    VideoEventType.OBJECT_APPEARED: "\033[32m",
    VideoEventType.OBJECT_VANISHED: "\033[31m",
    VideoEventType.OBJECT_PRESENT:  "\033[90m",
    VideoEventType.POSE_DETECTED:   "\033[90m",
    VideoEventType.GESTURE:         "\033[36m",
}
RESET = "\033[0m"

# 目标类别 → 固定颜色（BGR）
def class_color(name: str) -> tuple:
    palette = [C_GREEN, C_BLUE, C_ORANGE, C_PURPLE, C_YELLOW,
               (80, 200, 180), (180, 80, 200)]
    return palette[hash(name) % len(palette)]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  终端事件处理器（两种模式共用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class TerminalLogger:
    """
    把 PerceptionEvent 格式化打印到终端。
    quiet_types 里的事件只计数、不打印（避免刷屏）。
    """
    QUIET_DEFAULT = {VideoEventType.POSE_DETECTED, VideoEventType.OBJECT_PRESENT}

    def __init__(self, min_conf: float = 0.3, quiet_types: set | None = None):
        self.min_conf = min_conf
        self.quiet = quiet_types if quiet_types is not None else self.QUIET_DEFAULT
        self._counts: dict[str, int] = defaultdict(int)
        self._start = time.time()

    def __call__(self, ev: PerceptionEvent):
        if ev.confidence < self.min_conf:
            return
        self._counts[ev.type] += 1
        if ev.type in self.quiet:
            return

        p = ev.payload
        detail = ""
        if ev.type == VideoEventType.OBJECT_APPEARED:
            detail = f"  → {p.get('class','?')} #id={p.get('track_id','?')}  bbox={p.get('bbox')}"
        elif ev.type == VideoEventType.OBJECT_VANISHED:
            detail = f"  → {p.get('class','?')} #id={p.get('track_id','?')}  在场{p.get('duration_s','?')}s"
        elif ev.type == VideoEventType.GESTURE:
            detail = f"  → 【{p.get('gesture','?')}】"
        elif ev.type == VideoEventType.MOTION_DETECTED:
            detail = f"  → 面积={p.get('area_px','?')}px  区域={p.get('region_count','?')}"
        elif ev.type == VideoEventType.SCENE_CHANGE:
            detail = f"  → 变化率={p.get('change_ratio','?')}"

        color = TERM.get(ev.type, "")
        elapsed = ev.timestamp - self._start
        print(f"{color}[{elapsed:6.1f}s] {ev.source:18s} {ev.type:20s} "
              f"conf={ev.confidence:.2f}{detail}{RESET}")

    def summary(self):
        print("\n─── 事件统计 ───────────────────────────────")
        for t, c in sorted(self._counts.items(), key=lambda x: -x[1]):
            print(f"  {t:28s}: {c}")
        print("─────────────────────────────────────────────")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  OpenCV 绘图工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def draw_box(frame, x1, y1, x2, y2, color, label="", conf=0.0):
    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
    if label:
        text = f"{label} {conf:.0%}" if conf > 0 else label
        fs = 0.45
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        tx, ty = int(x1), max(int(y1) - 4, th + 4)
        cv2.rectangle(frame, (tx, ty - th - 4), (tx + tw + 6, ty + 2), color, -1)
        cv2.putText(frame, text, (tx + 3, ty - 1),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, C_WHITE, 1, cv2.LINE_AA)


def draw_motion_mask(frame, mask, alpha=0.25):
    if mask is None:
        return
    h, w = frame.shape[:2]
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    overlay = frame.copy()
    overlay[mask > 0] = C_GREEN
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_pose(frame, keypoints: dict):
    CONNECTIONS = [
        ("left_shoulder",  "right_shoulder"),
        ("left_shoulder",  "left_elbow"),   ("left_elbow",  "left_wrist"),
        ("right_shoulder", "right_elbow"),  ("right_elbow", "right_wrist"),
        ("left_hip",       "right_hip"),
        ("left_shoulder",  "left_hip"),     ("right_shoulder", "right_hip"),
    ]
    pts = {k: (int(v[0]), int(v[1])) for k, v in keypoints.items() if v}
    for a, b in CONNECTIONS:
        if a in pts and b in pts:
            cv2.line(frame, pts[a], pts[b], C_PURPLE, 2, cv2.LINE_AA)
    for name, pt in pts.items():
        dot = C_ORANGE if "wrist" in name else C_PURPLE
        cv2.circle(frame, pt, 5, dot, -1, cv2.LINE_AA)
        cv2.circle(frame, pt, 5, C_WHITE, 1, cv2.LINE_AA)


def put_text_bg(frame, text, x, y, fs=0.45, color=C_WHITE, bg=C_BLACK):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
    cv2.rectangle(frame, (x - 2, y - th - 3), (x + tw + 4, y + 3), bg, -1)
    cv2.putText(frame, text, (x + 1, y),
                cv2.FONT_HERSHEY_SIMPLEX, fs, color, 1, cv2.LINE_AA)


def draw_event_log(frame, log: deque, max_show=8):
    h, w = frame.shape[:2]
    x = w - 310
    for i, (ts, label, color) in enumerate(list(log)[:max_show]):
        a = max(0.0, 1.0 - (time.time() - ts) / 4.0)
        if a <= 0:
            continue
        c = tuple(int(v * a + 30 * (1 - a)) for v in color)
        put_text_bg(frame, label, x, 18 + i * 20, fs=0.40, color=c)


def draw_hud(frame, fps, total_events, n_objects, mode, paused):
    lines = [
        f"FPS  {fps:.0f}",
        f"evts {total_events}",
        f"objs {n_objects}",
        f"mode {'[1]all' if mode==1 else '[2]boxes' if mode==2 else '[3]motion'}",
        "PAUSED" if paused else "",
    ]
    for i, line in enumerate([l for l in lines if l]):
        put_text_bg(frame, line, 8, 18 + i * 20,
                    color=C_YELLOW if line == "PAUSED" else C_WHITE)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Viewer  ——  帧读取 + 检测 + 绘制 + 事件回调
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Viewer:
    """
    读取视频帧，逐帧运行感知检测器，叠加结果显示在 OpenCV 窗口中。
    每检测到事件都调用 on_event 回调（终端日志 / 后续注意力层均可接入）。
    """

    def __init__(self, args, on_event: callable):
        self.args = args
        self.on_event = on_event
        self.mode = 1
        self.paused = False
        self.event_log: deque = deque(maxlen=16)      # (ts, label, bgr_color)
        self.active_tracks: dict = {}                  # track_id → {cls, bbox, conf, keypoints}
        self._fps_times: deque = deque(maxlen=30)
        self._total_events = 0

        # ── 运动检测器（始终启用）──────────────────────────────────────
        from perception.video.motion_detector import MotionDetector
        self.motion = MotionDetector(motion_threshold=800, downsample=0.5)
        self._motion_mask: np.ndarray | None = None

        # ── YOLO（可选）──────────────────────────────────────────────
        self.yolo = None
        if not args.no_yolo:
            try:
                from ultralytics import YOLO
                self.yolo = YOLO(args.model)
                print(f"[viewer] YOLO 已加载: {args.model}")
            except Exception as e:
                print(f"[viewer] YOLO 不可用: {e}")

        # ── Pose（可选）──────────────────────────────────────────────
        self.pose_lm = None
        self._mp = None
        if not args.no_pose:
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision as mp_vision
                if os.path.exists(args.pose_model):
                    opts = mp_vision.PoseLandmarkerOptions(
                        base_options=mp_python.BaseOptions(
                            model_asset_path=args.pose_model),
                        running_mode=mp_vision.RunningMode.IMAGE,
                        num_poses=4,
                        min_pose_detection_confidence=0.5,
                    )
                    self.pose_lm = mp_vision.PoseLandmarker.create_from_options(opts)
                    self._mp = mp
                    print(f"[viewer] Pose 已加载: {args.pose_model}")
                else:
                    print(f"[viewer] Pose 模型不存在 ({args.pose_model})，跳过")
            except Exception as e:
                print(f"[viewer] Pose 不可用: {e}")

    # ── 主循环 ────────────────────────────────────────────────────────

    def run(self):
        source = self.args.source
        if isinstance(source, str) and source.isdigit():
            source = int(source)

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[viewer] 无法打开视频源: {source}")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        WIN = "Perception Viewer  [Q=退出  P=暂停  C=清除  S=截图  1/2/3=模式]"
        cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WIN, 1280, 720)
        print("[viewer] 窗口已打开")

        frame = None
        while True:
            if not self.paused:
                ret, frame = cap.read()
                if not ret:
                    break
                self._process(frame)

            if frame is not None:
                cv2.imshow(WIN, frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break
            elif key in (ord('p'), ord('P')):
                self.paused = not self.paused
            elif key in (ord('c'), ord('C')):
                self.event_log.clear()
                self.active_tracks.clear()
                self._total_events = 0
            elif key in (ord('s'), ord('S')) and frame is not None:
                fname = f"snapshot_{int(time.time())}.jpg"
                cv2.imwrite(fname, frame)
                print(f"[viewer] 截图保存: {fname}")
            elif key == ord('1'):
                self.mode = 1
            elif key == ord('2'):
                self.mode = 2
            elif key == ord('3'):
                self.mode = 3

        cap.release()
        cv2.destroyAllWindows()

    # ── 单帧处理 ─────────────────────────────────────────────────────

    def _process(self, frame: np.ndarray):
        # 1. 运动检测
        motion_evts = self.motion.process(frame)
        has_motion = any(e.type == VideoEventType.MOTION_DETECTED for e in motion_evts)
        for ev in motion_evts:
            self._emit(ev)
            if ev.type == VideoEventType.MOTION_DETECTED:
                small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                self._motion_mask = self.motion._bg.apply(small)
                self._vlog(f"motion  area={ev.payload['area_px']}", C_GREEN)
            elif ev.type == VideoEventType.SCENE_CHANGE:
                self._vlog(f"scene change  Δ={ev.payload['change_ratio']:.2f}", C_ORANGE)

        # 2. YOLO
        if self.yolo and (has_motion or self.args.always_detect):
            self._run_yolo(frame)

        # 3. Pose
        if self.pose_lm and (has_motion or self.args.always_detect):
            self._run_pose(frame)

        # 4. 绘制叠加层
        self._draw(frame)

        # FPS
        self._fps_times.append(time.perf_counter())

    def _run_yolo(self, frame: np.ndarray):
        results = self.yolo.track(
            source=frame, conf=self.args.conf, iou=0.5,
            persist=True, verbose=False, device=self.args.device,
        )
        if not results or results[0].boxes is None:
            self._flush_vanished(set())
            return

        boxes = results[0].boxes
        names = results[0].names
        current_ids: set[int] = set()

        for box in boxes:
            if box.id is None:
                continue
            tid   = int(box.id.item())
            cls   = names[int(box.cls.item())]
            conf  = float(box.conf.item())
            bbox  = [float(v) for v in box.xyxy[0].tolist()]
            current_ids.add(tid)

            is_new = tid not in self.active_tracks
            self.active_tracks[tid] = {"cls": cls, "bbox": bbox,
                                       "conf": conf, "keypoints": None,
                                       "first_seen": self.active_tracks.get(
                                           tid, {}).get("first_seen", time.time())}
            if is_new:
                ev = PerceptionEvent(
                    type=VideoEventType.OBJECT_APPEARED, modality="video",
                    confidence=conf, source="object_detector",
                    payload={"track_id": tid, "class": cls, "bbox": bbox},
                )
                self._emit(ev)
                self._vlog(f"appeared  {cls} #{tid}", class_color(cls))
            else:
                # 低频心跳
                duration = time.time() - self.active_tracks[tid]["first_seen"]
                if int(duration) % 5 == 0 and duration > 1:
                    ev = PerceptionEvent(
                        type=VideoEventType.OBJECT_PRESENT, modality="video",
                        confidence=conf, source="object_detector",
                        payload={"track_id": tid, "class": cls,
                                 "bbox": bbox, "duration_s": round(duration, 1)},
                    )
                    self._emit(ev)

        self._flush_vanished(current_ids)

    def _flush_vanished(self, current_ids: set):
        for tid in set(self.active_tracks) - current_ids:
            state = self.active_tracks.pop(tid)
            dur = round(time.time() - state["first_seen"], 1)
            ev = PerceptionEvent(
                type=VideoEventType.OBJECT_VANISHED, modality="video",
                confidence=0.9, source="object_detector",
                payload={"track_id": tid, "class": state["cls"],
                         "bbox": state["bbox"], "duration_s": dur},
            )
            self._emit(ev)
            self._vlog(f"vanished  {state['cls']} #{tid}", (50, 60, 220))

    def _run_pose(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self.pose_lm.detect(mp_img)
        if not result.pose_landmarks:
            return

        h, w = frame.shape[:2]
        for pose_lm in result.pose_landmarks:
            def px(idx):
                p = pose_lm[idx]
                return [p.x * w, p.y * h]

            kp = {
                "nose":           px(0),
                "left_shoulder":  px(11), "right_shoulder": px(12),
                "left_elbow":     px(13), "right_elbow":    px(14),
                "left_wrist":     px(15), "right_wrist":    px(16),
                "left_hip":       px(23), "right_hip":      px(24),
            }

            # 发出姿态事件
            ev = PerceptionEvent(
                type=VideoEventType.POSE_DETECTED, modality="video",
                confidence=0.7, source="pose_detector",
                payload={"keypoints": {k: [round(v[0],1), round(v[1],1)]
                                       for k, v in kp.items()}},
            )
            self._emit(ev)

            # 绑定姿态到对应 YOLO track（鼻子落在 bbox 内）
            nose = kp["nose"]
            matched = False
            for tid, track in self.active_tracks.items():
                x1, y1, x2, y2 = track["bbox"]
                if x1 <= nose[0] <= x2 and y1 <= nose[1] <= y2:
                    track["keypoints"] = kp
                    matched = True
                    break
            if not matched:
                draw_pose(frame, kp)   # 无对应 bbox，直接画

            # 手势规则
            for gesture, condition in [
                ("raise_hand_left",  kp["left_wrist"][1]  < nose[1]),
                ("raise_hand_right", kp["right_wrist"][1] < nose[1]),
            ]:
                if condition and nose[1] > 0:
                    gev = PerceptionEvent(
                        type=VideoEventType.GESTURE, modality="video",
                        confidence=0.8, source="pose_detector",
                        payload={"gesture": gesture},
                    )
                    self._emit(gev)
                    self._vlog(f"gesture  {gesture}", C_PURPLE)

    # ── 绘制 ─────────────────────────────────────────────────────────

    def _draw(self, frame: np.ndarray):
        # 运动遮罩
        if self.mode in (1, 3):
            draw_motion_mask(frame, self._motion_mask)

        # 检测框 + 姿态骨架
        if self.mode in (1, 2):
            for tid, track in self.active_tracks.items():
                x1, y1, x2, y2 = track["bbox"]
                color = class_color(track["cls"])
                draw_box(frame, x1, y1, x2, y2, color,
                         label=f"{track['cls']} #{tid}", conf=track["conf"])
                if track.get("keypoints") and self.mode == 1:
                    draw_pose(frame, track["keypoints"])

        # HUD + 事件日志
        fps = ((len(self._fps_times) - 1) /
               max(self._fps_times[-1] - self._fps_times[0], 1e-6)
               if len(self._fps_times) >= 2 else 0)
        draw_hud(frame, fps, self._total_events,
                 len(self.active_tracks), self.mode, self.paused)
        if self.mode in (1, 2):
            draw_event_log(frame, self.event_log)

    # ── 工具 ─────────────────────────────────────────────────────────

    def _emit(self, ev: PerceptionEvent):
        """发出事件：同时给终端日志和后续注意力层"""
        self._total_events += 1
        self.on_event(ev)

    def _vlog(self, msg: str, color: tuple):
        """写入视频右上角事件日志"""
        self.event_log.appendleft((time.time(), msg, color))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  终端模式（无窗口，使用 VideoPipeline 后台线程）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_headless(args, logger: TerminalLogger):
    source = args.source
    if isinstance(source, str) and source.isdigit():
        source = int(source)

    pipeline = VideoPipeline(
        source=source,
        enable_yolo=not args.no_yolo,
        enable_pose=not args.no_pose,
        target_fps=args.fps,
        yolo_device=args.device,
    ).start(logger)

    print("▶  终端模式启动（Ctrl+C 退出）\n")
    try:
        while True:
            time.sleep(2)
            s = pipeline.stats
            if s["frames"] > 0:
                print(f"\033[90m  fps={s['fps']}  "
                      f"frames={s['frames']}  events={s['events']}\033[0m",
                      end="\r")
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    ap = argparse.ArgumentParser(description="结构化感知系统")
    # 视频源
    ap.add_argument("--source",        default="0",
                    help="摄像头 id(0) / 视频文件 / RTSP URL")
    # 检测器
    ap.add_argument("--model",         default="yolo11n.pt",
                    help="YOLO 模型文件（如 yolo11n.pt / yolov8n.pt）")
    ap.add_argument("--pose-model",    default="pose_landmarker_lite.task",
                    help="MediaPipe Pose 模型文件")
    ap.add_argument("--conf",          type=float, default=0.4,
                    help="YOLO 检测置信度阈值")
    ap.add_argument("--device",        default="cpu",
                    help="推理设备: cpu / cuda / mps")
    ap.add_argument("--no-yolo",       action="store_true")
    ap.add_argument("--no-pose",       action="store_true")
    ap.add_argument("--always-detect", action="store_true",
                    help="无论有无运动都跑 YOLO/Pose")
    # 运行模式
    ap.add_argument("--no-view",       action="store_true",
                    help="不打开窗口，纯终端输出（服务器模式）")
    ap.add_argument("--fps",           type=int, default=30,
                    help="目标帧率（仅终端模式有效）")
    # 事件过滤
    ap.add_argument("--min-conf",      type=float, default=0.3,
                    help="终端只打印 conf≥此值的事件")

    args = ap.parse_args()

    logger = TerminalLogger(min_conf=args.min_conf)

    print("━" * 50)
    print("  Perception System")
    print(f"  source={args.source}  yolo={not args.no_yolo}"
          f"  pose={not args.no_pose}  view={not args.no_view}")
    print("━" * 50 + "\n")

    try:
        if args.no_view:
            run_headless(args, logger)
        else:
            Viewer(args, on_event=logger).run()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n")
        logger.summary()
        print("■  停止")


if __name__ == "__main__":
    main()