"""
perception/video/motion_detector.py
运动检测模块 —— 背景减除 + 帧差，CPU 即可，延迟 <5ms
输出事件：motion_detected, scene_change
"""
from __future__ import annotations
import cv2
import numpy as np
from ..event import PerceptionEvent, VideoEventType


class MotionDetector:
    """
    背景减除运动检测器

    参数
    ----
    motion_threshold    触发 motion_detected 的前景像素数下限
    scene_change_ratio  触发 scene_change 的帧差均值占比 (0~1)
    downsample          处理前缩小倍率，加快速度
    history             MOG2 背景建模帧数
    """

    SOURCE = "motion_detector"

    def __init__(
        self,
        motion_threshold: int = 800,
        scene_change_ratio: float = 0.15,
        downsample: float = 0.5,
        history: int = 200,
    ):
        self.motion_threshold = motion_threshold
        self.scene_change_ratio = scene_change_ratio
        self.ds = downsample

        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=40,
            detectShadows=False,
        )
        self._prev_gray: np.ndarray | None = None

    # ── 公开接口 ────────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> list[PerceptionEvent]:
        """输入 BGR 帧，返回事件列表（可能为空）"""
        events: list[PerceptionEvent] = []
        small = cv2.resize(frame, (0, 0), fx=self.ds, fy=self.ds)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        events.extend(self._detect_motion(small, gray))
        events.extend(self._detect_scene_change(gray))

        self._prev_gray = gray
        return events

    # ── 内部检测 ────────────────────────────────────────────────────────

    def _detect_motion(self, small: np.ndarray, gray: np.ndarray) -> list[PerceptionEvent]:
        mask = self._bg.apply(small)
        area = cv2.countNonZero(mask)
        if area < self.motion_threshold:
            return []

        # 找各个运动区域（供注意力层聚焦用）
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        regions = [
            list(cv2.boundingRect(c))           # [x, y, w, h]，按 downsample 坐标
            for c in contours
            if cv2.contourArea(c) > 150
        ]

        return [PerceptionEvent(
            type=VideoEventType.MOTION_DETECTED,
            modality="video",
            confidence=min(area / 6000, 1.0),
            source=self.SOURCE,
            payload={
                "area_px": area,
                "regions": regions,             # 运动区域列表（缩放坐标系）
                "region_count": len(regions),
            },
        )]

    def _detect_scene_change(self, gray: np.ndarray) -> list[PerceptionEvent]:
        if self._prev_gray is None:
            return []
        diff = cv2.absdiff(gray, self._prev_gray)
        ratio = diff.mean() / 255.0
        if ratio < self.scene_change_ratio:
            return []

        return [PerceptionEvent(
            type=VideoEventType.SCENE_CHANGE,
            modality="video",
            confidence=min(ratio / 0.4, 1.0),
            source=self.SOURCE,
            payload={"change_ratio": round(ratio, 4)},
        )]
