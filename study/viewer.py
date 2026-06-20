"""
viewer.py  ——  摄像头实时可视化

把感知流水线的检测结果直接画在视频画面上，本地运行即可看到。

依赖（在你本机安装）：
    pip install ultralytics mediapipe opencv-python

运行：
    python viewer.py                     # 默认摄像头
    python viewer.py --source video.mp4  # 视频文件
    python viewer.py --source rtsp://... # RTSP 流
    python viewer.py --no-yolo           # 只跑运动检测（最轻量）

按键：
    Q / ESC  退出
    P        暂停 / 继续
    C        清除事件日志
    1~3      切换显示模式（1=全部叠加  2=仅检测框  3=仅运动）
"""
from __future__ import annotations
import argparse
import time
import math
from collections import deque

import cv2
import numpy as np


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  颜色表（BGR）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C_GREEN   = (60, 200, 80)
C_BLUE    = (220, 140, 50)
C_ORANGE  = (30, 140, 220)
C_PURPLE  = (200, 100, 180)
C_RED     = (50, 60, 220)
C_GRAY    = (140, 140, 140)
C_WHITE   = (240, 240, 240)
C_BLACK   = (0, 0, 0)
C_YELLOW  = (30, 220, 220)

# 目标类别 → 固定颜色（按 COCO 类别 id 哈希）
def class_color(class_name: str) -> tuple:
    h = hash(class_name) % 7
    palette = [C_GREEN, C_BLUE, C_ORANGE, C_PURPLE, C_YELLOW,
               (80, 200, 180), (180, 80, 200)]
    return palette[h]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  绘图工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def draw_box(frame, x1, y1, x2, y2, color, label="", conf=0.0, thickness=2):
    """画检测框 + 角标标签"""
    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, thickness)

    if label:
        text = f"{label} {conf:.0%}" if conf > 0 else label
        fs = 0.45
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        tx, ty = int(x1), max(int(y1) - 4, th + 4)
        cv2.rectangle(frame, (tx, ty - th - 4), (tx + tw + 6, ty + 2), color, -1)
        cv2.putText(frame, text, (tx + 3, ty - 1),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, C_WHITE, 1, cv2.LINE_AA)


def draw_motion_mask(frame, mask, color=C_GREEN, alpha=0.25):
    """把运动前景区域半透明叠加在画面上"""
    if mask is None:
        return
    h, w = frame.shape[:2]
    mh, mw = mask.shape[:2]
    if mh != h or mw != w:
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
    overlay = frame.copy()
    overlay[mask > 0] = color
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_pose(frame, keypoints: dict, color=C_PURPLE):
    """画人体姿态关键点（MediaPipe 输出的像素坐标）"""
    CONNECTIONS = [
        ("left_shoulder", "right_shoulder"),
        ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
        ("left_hip", "right_hip"),
        ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ]
    pts = {k: (int(v[0]), int(v[1])) for k, v in keypoints.items() if v}

    for a, b in CONNECTIONS:
        if a in pts and b in pts:
            cv2.line(frame, pts[a], pts[b], color, 2, cv2.LINE_AA)

    for name, pt in pts.items():
        dot_color = C_ORANGE if "wrist" in name else color
        cv2.circle(frame, pt, 5, dot_color, -1, cv2.LINE_AA)
        cv2.circle(frame, pt, 5, C_WHITE, 1, cv2.LINE_AA)


def put_text_bg(frame, text, x, y, font_scale=0.45, color=C_WHITE, bg=C_BLACK):
    """带背景色的文字"""
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
    cv2.rectangle(frame, (x - 2, y - th - 3), (x + tw + 4, y + 3), bg, -1)
    cv2.putText(frame, text, (x + 1, y),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1, cv2.LINE_AA)


def draw_event_log(frame, log: deque, max_show=6):
    """右上角显示最近事件"""
    h, w = frame.shape[:2]
    x = w - 300
    y_start = 16
    lh = 20

    for i, (ts, label, color) in enumerate(list(log)[:max_show]):
        age = time.time() - ts
        alpha_val = max(0.0, 1.0 - age / 4.0)   # 4 秒淡出
        if alpha_val <= 0:
            continue
        c = tuple(int(v * alpha_val + 50 * (1 - alpha_val)) for v in color)
        put_text_bg(frame, label, x, y_start + i * lh,
                    font_scale=0.4, color=c,
                    bg=(0, 0, 0))


def draw_hud(frame, stats: dict, mode: int, paused: bool):
    """左上角 HUD：帧率、事件计数、模式"""
    lines = [
        f"FPS {stats.get('fps', 0):.0f}",
        f"events {stats.get('total', 0)}",
        f"objects {stats.get('objects', 0)}",
        f"mode {'[1]all' if mode==1 else '[2]boxes' if mode==2 else '[3]motion'}",
    ]
    if paused:
        lines.insert(0, "PAUSED")

    for i, line in enumerate(lines):
        put_text_bg(frame, line, 8, 18 + i * 20,
                    font_scale=0.45,
                    color=C_YELLOW if (i == 0 and paused) else C_WHITE,
                    bg=(0, 0, 0))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  核心：逐帧处理 + 绘制
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Viewer:
    def __init__(self, args):
        self.args = args
        self.mode = 1           # 1=全部  2=仅框  3=仅运动
        self.paused = False
        self.event_log: deque = deque(maxlen=12)   # (ts, label_str, color)
        self.active_tracks: dict = {}              # track_id → {cls, bbox, conf, keypoints}
        self.stats = {"fps": 0.0, "total": 0, "objects": 0}

        # 运动检测（始终启用）
        from perception.video.motion_detector import MotionDetector
        self.motion = MotionDetector(
            motion_threshold=800,
            scene_change_ratio=0.15,
            downsample=0.5,
        )
        self._last_motion_mask: np.ndarray | None = None
        self._last_motion_events: list = []

        # YOLO（可选）
        self.yolo = None
        if not args.no_yolo:
            try:
                from ultralytics import YOLO
                self.yolo = YOLO(args.model)
                print(f"[viewer] YOLO 加载: {args.model}")
            except Exception as e:
                print(f"[viewer] YOLO 不可用: {e}")

        # Pose（可选）
        self.pose_lm = None
        if not args.no_pose:
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision as mp_vision
                import os
                model_path = args.pose_model
                if os.path.exists(model_path):
                    opts = mp_vision.PoseLandmarkerOptions(
                        base_options=mp_python.BaseOptions(model_asset_path=model_path),
                        running_mode=mp_vision.RunningMode.IMAGE,
                        num_poses=4,
                        min_pose_detection_confidence=0.5,
                    )
                    self.pose_lm = mp_vision.PoseLandmarker.create_from_options(opts)
                    self._mp = mp
                    print(f"[viewer] Pose 加载: {model_path}")
                else:
                    print(f"[viewer] Pose 模型不存在 ({model_path})，跳过")
            except Exception as e:
                print(f"[viewer] Pose 不可用: {e}")

        # FPS 计算
        self._fps_times: deque = deque(maxlen=30)

    # ── 主入口 ──────────────────────────────────────────────────────────

    def run(self):
        source = self.args.source
        if isinstance(source, str) and source.isdigit():
            source = int(source)

        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"[viewer] 无法打开视频源: {source}")
            return

        # 尝试设置分辨率
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        win = "Perception Viewer  [Q=退出  P=暂停  C=清除  1/2/3=模式]"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, 1280, 720)

        print("[viewer] 窗口已打开，按 Q 或 ESC 退出")

        while True:
            if not self.paused:
                ret, frame = cap.read()
                if not ret:
                    break
                self._process(frame)

            cv2.imshow(win, frame if not self.paused else frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):    # Q / ESC
                break
            elif key in (ord('p'), ord('P')):
                self.paused = not self.paused
            elif key in (ord('c'), ord('C')):
                self.event_log.clear()
                self.active_tracks.clear()
                self.stats['total'] = 0
            elif key == ord('1'):
                self.mode = 1
            elif key == ord('2'):
                self.mode = 2
            elif key == ord('3'):
                self.mode = 3

        cap.release()
        cv2.destroyAllWindows()
        print("[viewer] 退出")

    # ── 单帧处理 + 绘制 ─────────────────────────────────────────────────

    def _process(self, frame: np.ndarray):
        t0 = time.perf_counter()

        # ① 运动检测
        motion_evts = self.motion.process(frame)
        has_motion = any(e.type == "motion_detected" for e in motion_evts)
        self._handle_motion(frame, motion_evts)

        # ② YOLO（有运动时才跑，节省 CPU）
        if self.yolo and (has_motion or self.args.always_detect):
            self._handle_yolo(frame)

        # ③ Pose
        if self.pose_lm and (has_motion or self.args.always_detect):
            self._handle_pose(frame)

        # ④ 绘制所有叠加层
        self._draw(frame)

        # FPS
        self._fps_times.append(time.perf_counter())
        if len(self._fps_times) >= 2:
            dur = self._fps_times[-1] - self._fps_times[0]
            self.stats["fps"] = (len(self._fps_times) - 1) / max(dur, 1e-6)
        self.stats["objects"] = len(self.active_tracks)

    def _handle_motion(self, frame, events):
        for ev in events:
            if ev.type == "motion_detected":
                # 保存前景 mask 供绘制用（重建一次）
                small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                mask = self.motion._bg.apply(small)
                self._last_motion_mask = mask
                self._log(f"motion  area={ev.payload['area_px']}", C_GREEN)
                self.stats['total'] += 1
            elif ev.type == "scene_change":
                self._log(f"scene change  Δ={ev.payload['change_ratio']:.2f}", C_ORANGE)
                self.stats['total'] += 1

    def _handle_yolo(self, frame):
        results = self.yolo.track(
            source=frame, conf=self.args.conf, iou=0.5,
            persist=True, verbose=False, device=self.args.device,
        )
        if not results or results[0].boxes is None:
            return

        current_ids = set()
        boxes = results[0].boxes
        names = results[0].names

        for box in boxes:
            if box.id is None:
                continue
            tid = int(box.id.item())
            cls = names[int(box.cls.item())]
            conf = float(box.conf.item())
            bbox = [float(v) for v in box.xyxy[0].tolist()]
            current_ids.add(tid)

            is_new = tid not in self.active_tracks
            self.active_tracks[tid] = {
                "cls": cls, "bbox": bbox, "conf": conf, "keypoints": None
            }
            if is_new:
                self._log(f"appeared  {cls} #{tid}", class_color(cls))
                self.stats['total'] += 1

        # 消失目标
        gone = set(self.active_tracks) - current_ids
        for tid in gone:
            cls = self.active_tracks[tid]["cls"]
            self._log(f"vanished  {cls} #{tid}", C_RED)
            self.stats['total'] += 1
            del self.active_tracks[tid]

    def _handle_pose(self, frame):
        import mediapipe as mp
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
            # 绑定到最近的 YOLO 目标（简单匹配：鼻子落在哪个 bbox 里）
            nose = kp["nose"]
            matched = False
            for tid, track in self.active_tracks.items():
                x1, y1, x2, y2 = track["bbox"]
                if x1 <= nose[0] <= x2 and y1 <= nose[1] <= y2:
                    track["keypoints"] = kp
                    matched = True
                    break
            if not matched:
                # 直接画在画面上（没有对应 bbox 时）
                draw_pose(frame, kp)

            # 手势判断
            if nose[1] > 0:
                if kp["left_wrist"][1] < nose[1]:
                    self._log("gesture  raise_hand_left", C_PURPLE)
                if kp["right_wrist"][1] < nose[1]:
                    self._log("gesture  raise_hand_right", C_PURPLE)

    def _draw(self, frame):
        # 运动遮罩
        if self.mode in (1, 3) and self._last_motion_mask is not None:
            draw_motion_mask(frame, self._last_motion_mask, color=C_GREEN)

        # 检测框 + 姿态
        if self.mode in (1, 2):
            for tid, track in self.active_tracks.items():
                x1, y1, x2, y2 = track["bbox"]
                color = class_color(track["cls"])
                draw_box(frame, x1, y1, x2, y2, color,
                         label=f"{track['cls']} #{tid}",
                         conf=track["conf"])
                if track.get("keypoints") and self.mode == 1:
                    draw_pose(frame, track["keypoints"])

        # HUD + 事件日志
        draw_hud(frame, self.stats, self.mode, self.paused)
        if self.mode in (1, 2):
            draw_event_log(frame, self.event_log)

    def _log(self, msg: str, color: tuple):
        self.event_log.appendleft((time.time(), msg, color))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    ap = argparse.ArgumentParser(description="感知系统摄像头可视化")
    ap.add_argument("--source",        default="0",   help="摄像头 id 或视频路径/RTSP URL")
    ap.add_argument("--model",         default="yolo11n.pt", help="YOLO 模型文件")
    ap.add_argument("--pose-model",    default="pose_landmarker_lite.task")
    ap.add_argument("--conf",          type=float, default=0.4, help="YOLO 检测置信度")
    ap.add_argument("--device",        default="cpu",  help="cpu / cuda / mps")
    ap.add_argument("--no-yolo",       action="store_true", help="禁用 YOLO")
    ap.add_argument("--no-pose",       action="store_true", help="禁用姿态检测")
    ap.add_argument("--always-detect", action="store_true", help="无论有无运动都跑检测器")
    args = ap.parse_args()

    Viewer(args).run()


if __name__ == "__main__":
    main()