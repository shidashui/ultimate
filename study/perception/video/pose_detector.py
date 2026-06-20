"""
perception/video/pose_detector.py
姿态 + 手势检测模块 —— MediaPipe 0.10+ Tasks API，CPU 5~15ms/帧
输出事件：pose_detected / gesture

内置手势规则（可扩展）：
  raise_hand_left / raise_hand_right  : 手腕高于鼻子
  arms_wide                           : 双肘横向距离 > 帧宽 60%
  arms_crossed                        : 双手腕交叉越过身体中线

MediaPipe 0.10+ 需要下载模型文件：
  wget https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
"""
from __future__ import annotations
import numpy as np
import cv2
from pathlib import Path

try:
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision
    _MP_AVAILABLE = True
except ImportError:
    _MP_AVAILABLE = False

from ..event import PerceptionEvent, VideoEventType

# MediaPipe 0.10+ 关键点索引
_NOSE           = 0
_LEFT_SHOULDER  = 11
_RIGHT_SHOULDER = 12
_LEFT_ELBOW     = 13
_RIGHT_ELBOW    = 14
_LEFT_WRIST     = 15
_RIGHT_WRIST    = 16
_LEFT_HIP       = 23
_RIGHT_HIP      = 24


class PoseDetector:
    SOURCE = "pose_detector"

    # 默认模型路径（用户需自行下载，见模块注释）
    DEFAULT_MODEL = "pose_landmarker_lite.task"

    def __init__(
        self,
        model_path: str | None = None,
        gesture_cooldown_frames: int = 15,
    ):
        if not _MP_AVAILABLE:
            raise RuntimeError("请先安装 mediapipe: pip install mediapipe")

        model = model_path or self.DEFAULT_MODEL
        if not Path(model).exists():
            raise RuntimeError(
                f"姿态模型文件不存在: {model}\n"
                "请下载：\n"
                "  wget https://storage.googleapis.com/mediapipe-models/"
                "pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
            )

        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model),
            running_mode=mp_vision.RunningMode.IMAGE,
            num_poses=4,
            min_pose_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._cooldown = gesture_cooldown_frames
        self._last_gesture_frame: dict[str, int] = {}
        self._frame_count = 0

    # ── 公开接口 ────────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> list[PerceptionEvent]:
        self._frame_count += 1
        events: list[PerceptionEvent] = []
        h, w = frame.shape[:2]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)

        if not result.pose_landmarks:
            return events

        for pose_lm in result.pose_landmarks:
            def px(idx):
                p = pose_lm[idx]
                return p.x * w, p.y * h, p.visibility if hasattr(p, 'visibility') else 1.0

            nose        = px(_NOSE)
            l_wrist     = px(_LEFT_WRIST)
            r_wrist     = px(_RIGHT_WRIST)
            l_elbow     = px(_LEFT_ELBOW)
            r_elbow     = px(_RIGHT_ELBOW)
            l_hip       = px(_LEFT_HIP)
            r_hip       = px(_RIGHT_HIP)
            l_shoulder  = px(_LEFT_SHOULDER)
            r_shoulder  = px(_RIGHT_SHOULDER)

            keypoints = {
                "nose":        [round(nose[0], 1), round(nose[1], 1)],
                "left_wrist":  [round(l_wrist[0], 1), round(l_wrist[1], 1)],
                "right_wrist": [round(r_wrist[0], 1), round(r_wrist[1], 1)],
                "left_hip":    [round(l_hip[0], 1), round(l_hip[1], 1)],
                "right_hip":   [round(r_hip[0], 1), round(r_hip[1], 1)],
            }

            events.append(PerceptionEvent(
                type=VideoEventType.POSE_DETECTED,
                modality="video",
                confidence=min(nose[2], l_shoulder[2], r_shoulder[2]),
                source=self.SOURCE,
                payload={"keypoints": keypoints},
            ))

            events.extend(self._check_gestures(
                nose, l_wrist, r_wrist,
                l_elbow, r_elbow,
                l_shoulder, r_shoulder, w
            ))

        return events

    # ── 手势规则 ────────────────────────────────────────────────────────

    def _check_gestures(self, nose, l_wrist, r_wrist,
                        l_elbow, r_elbow,
                        l_shoulder, r_shoulder, frame_width) -> list[PerceptionEvent]:
        events = []

        if l_wrist[2] > 0.5 and l_wrist[1] < nose[1]:
            events.extend(self._emit_gesture("raise_hand_left", 0.85, {
                "wrist_y": l_wrist[1], "nose_y": nose[1]
            }))

        if r_wrist[2] > 0.5 and r_wrist[1] < nose[1]:
            events.extend(self._emit_gesture("raise_hand_right", 0.85, {
                "wrist_y": r_wrist[1], "nose_y": nose[1]
            }))

        elbow_span = abs(l_elbow[0] - r_elbow[0])
        if l_elbow[2] > 0.4 and r_elbow[2] > 0.4 and elbow_span > frame_width * 0.6:
            events.extend(self._emit_gesture("arms_wide", 0.75, {
                "elbow_span_ratio": round(elbow_span / frame_width, 2)
            }))

        mid_x = (l_shoulder[0] + r_shoulder[0]) / 2
        if (l_wrist[2] > 0.5 and r_wrist[2] > 0.5
                and l_wrist[0] > mid_x and r_wrist[0] < mid_x):
            events.extend(self._emit_gesture("arms_crossed", 0.7, {"mid_x": round(mid_x, 1)}))

        return events

    def _emit_gesture(self, name: str, conf: float, payload: dict) -> list[PerceptionEvent]:
        last = self._last_gesture_frame.get(name, -9999)
        if self._frame_count - last < self._cooldown:
            return []
        self._last_gesture_frame[name] = self._frame_count
        return [PerceptionEvent(
            type=VideoEventType.GESTURE,
            modality="video",
            confidence=conf,
            source=self.SOURCE,
            payload={"gesture": name, **payload},
        )]
