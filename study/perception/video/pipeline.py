"""
perception/video/pipeline.py
视频感知流水线 —— 串联所有视频检测器，统一输出事件

使用方式
-------
pipeline = VideoPipeline(source=0, enable_pose=True)
pipeline.start(on_event=lambda e: print(e))
# ... 运行中 ...
pipeline.stop()

帧处理顺序
----------
1. MotionDetector  : 背景减除，最轻量
2. ObjectDetector  : YOLO 目标检测 + 追踪（可关闭）
3. PoseDetector    : MediaPipe 姿态（可关闭）

只有在 MotionDetector 检测到运动时，才调用后两个检测器
（节省 CPU/GPU，同时贴近"有变化才注意"的人类感知模式）
"""
from __future__ import annotations
import threading
import time
from typing import Callable

import cv2
import numpy as np

from ..event import PerceptionEvent
from .motion_detector import MotionDetector
from .object_detector import ObjectDetector
from .pose_detector import PoseDetector


EventCallback = Callable[[PerceptionEvent], None]


class VideoPipeline:
    def __init__(
        self,
        source: int | str = 0,          # 摄像头 id 或视频路径/RTSP URL
        enable_yolo: bool = True,
        enable_pose: bool = True,
        # 运动检测参数
        motion_threshold: int = 800,
        # YOLO 参数
        yolo_model: str = "yolo11n.pt",
        yolo_conf: float = 0.4,
        yolo_device: str = "cpu",
        # 流水线参数
        target_fps: int = 30,
        always_run_detectors: bool = False,  # True = 不管有无运动都跑 YOLO/Pose
    ):
        self._source = source
        self._target_fps = target_fps
        self._always_run = always_run_detectors

        self._motion = MotionDetector(motion_threshold=motion_threshold)
        self._yolo: ObjectDetector | None = None
        self._pose: PoseDetector | None = None

        if enable_yolo:
            self._yolo = ObjectDetector(
                model_path=yolo_model,
                conf=yolo_conf,
                device=yolo_device,
            )
        if enable_pose:
            try:
                self._pose = PoseDetector()
            except RuntimeError as e:
                print(f"[VideoPipeline] Pose 禁用: {e}")

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._callback: EventCallback | None = None

        # 统计
        self.stats = {"frames": 0, "events": 0, "fps": 0.0}

    # ── 生命周期 ─────────────────────────────────────────────────────────

    def start(self, on_event: EventCallback) -> "VideoPipeline":
        """启动后台线程，事件通过 on_event 回调返回"""
        self._callback = on_event
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop()

    # ── 主循环 ───────────────────────────────────────────────────────────

    def _loop(self):
        cap = cv2.VideoCapture(self._source)
        if not cap.isOpened():
            print(f"[VideoPipeline] 无法打开视频源: {self._source}")
            return

        interval = 1.0 / self._target_fps
        fps_window: list[float] = []

        try:
            while not self._stop_event.is_set():
                t0 = time.perf_counter()
                ret, frame = cap.read()
                if not ret:
                    break

                self.stats["frames"] += 1
                events = self._process_frame(frame)
                self.stats["events"] += len(events)

                for ev in events:
                    if self._callback:
                        self._callback(ev)

                # 帧率统计
                elapsed = time.perf_counter() - t0
                fps_window.append(1.0 / max(elapsed, 1e-6))
                if len(fps_window) > 30:
                    fps_window.pop(0)
                    self.stats["fps"] = round(sum(fps_window) / len(fps_window), 1)

                # 控速
                sleep_t = interval - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)
        finally:
            cap.release()

    def _process_frame(self, frame: np.ndarray) -> list[PerceptionEvent]:
        events: list[PerceptionEvent] = []

        # 1. 运动检测（始终运行）
        motion_events = self._motion.process(frame)
        events.extend(motion_events)

        has_motion = any(e.type == "motion_detected" for e in motion_events)

        # 2. YOLO + Pose：仅在有运动时触发（或 always_run=True）
        if has_motion or self._always_run:
            if self._yolo:
                events.extend(self._yolo.process(frame))
            if self._pose:
                events.extend(self._pose.process(frame))

        return events
