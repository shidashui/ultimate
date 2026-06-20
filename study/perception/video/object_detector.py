"""
perception/video/object_detector.py
目标检测 + 追踪模块 —— YOLOv11 + ByteTrack
输出事件：object_appeared / object_vanished / object_present

object_appeared  : 新 track_id 首次出现
object_vanished  : 某 track_id 从画面消失
object_present   : 每隔 heartbeat_interval 帧发送一次"仍在场"心跳
"""
from __future__ import annotations
import time
from collections import defaultdict
from typing import NamedTuple

import numpy as np
from ultralytics import YOLO

from ..event import PerceptionEvent, VideoEventType


class _TrackState(NamedTuple):
    cls_name: str
    first_seen: float
    last_bbox: list[float]   # [x1, y1, x2, y2]，原始帧坐标


class ObjectDetector:
    """
    YOLOv11 + ByteTrack 目标追踪

    参数
    ----
    model_path          YOLO 模型路径或名称，如 "yolo11n.pt"
    conf                检测置信度阈值
    iou                 NMS IoU 阈值
    heartbeat_interval  每隔多少帧发送一次 object_present 心跳
    classes             限定检测类别 id 列表，None 表示检测全部
    device              "cpu" / "cuda" / "mps"
    """

    SOURCE = "object_detector"

    def __init__(
        self,
        model_path: str = "yolo11n.pt",
        conf: float = 0.4,
        iou: float = 0.5,
        heartbeat_interval: int = 30,
        classes: list[int] | None = None,
        device: str = "cpu",
    ):
        self._model = YOLO(model_path)
        self._conf = conf
        self._iou = iou
        self._heartbeat_interval = heartbeat_interval
        self._classes = classes
        self._device = device

        # track_id → _TrackState
        self._active: dict[int, _TrackState] = {}
        self._frame_count = 0

    # ── 公开接口 ────────────────────────────────────────────────────────

    def process(self, frame: np.ndarray) -> list[PerceptionEvent]:
        self._frame_count += 1
        events: list[PerceptionEvent] = []

        results = self._model.track(
            source=frame,
            conf=self._conf,
            iou=self._iou,
            classes=self._classes,
            persist=True,           # 跨帧保持 track_id
            verbose=False,
            device=self._device,
        )

        if not results or results[0].boxes is None:
            events.extend(self._flush_vanished(set()))
            return events

        boxes = results[0].boxes
        class_names = results[0].names
        current_ids: set[int] = set()

        for box in boxes:
            if box.id is None:
                continue
            track_id = int(box.id.item())
            cls_id = int(box.cls.item())
            cls_name = class_names[cls_id]
            conf = float(box.conf.item())
            bbox = box.xyxy[0].tolist()   # [x1, y1, x2, y2]

            current_ids.add(track_id)

            if track_id not in self._active:
                # 首次出现
                self._active[track_id] = _TrackState(
                    cls_name=cls_name,
                    first_seen=time.time(),
                    last_bbox=bbox,
                )
                events.append(self._make_event(
                    VideoEventType.OBJECT_APPEARED,
                    track_id, cls_name, conf, bbox,
                    extra={"first_seen": self._active[track_id].first_seen},
                ))
            else:
                # 更新位置
                old = self._active[track_id]
                self._active[track_id] = _TrackState(
                    cls_name=old.cls_name,
                    first_seen=old.first_seen,
                    last_bbox=bbox,
                )
                # 心跳
                if self._frame_count % self._heartbeat_interval == 0:
                    duration = time.time() - old.first_seen
                    events.append(self._make_event(
                        VideoEventType.OBJECT_PRESENT,
                        track_id, cls_name, conf, bbox,
                        extra={"duration_s": round(duration, 2)},
                    ))

        events.extend(self._flush_vanished(current_ids))
        return events

    # ── 内部辅助 ────────────────────────────────────────────────────────

    def _flush_vanished(self, current_ids: set[int]) -> list[PerceptionEvent]:
        """把不再出现的 track_id 标记为消失"""
        events = []
        gone = set(self._active) - current_ids
        for track_id in gone:
            state = self._active.pop(track_id)
            duration = time.time() - state.first_seen
            events.append(self._make_event(
                VideoEventType.OBJECT_VANISHED,
                track_id, state.cls_name,
                confidence=0.9,
                bbox=state.last_bbox,
                extra={"duration_s": round(duration, 2)},
            ))
        return events

    def _make_event(
        self,
        event_type: str,
        track_id: int,
        cls_name: str,
        confidence: float,
        bbox: list[float],
        extra: dict | None = None,
    ) -> PerceptionEvent:
        payload = {
            "track_id": track_id,
            "class": cls_name,
            "bbox": [round(v, 1) for v in bbox],
        }
        if extra:
            payload.update(extra)
        return PerceptionEvent(
            type=event_type,
            modality="video",
            confidence=confidence,
            source=self.SOURCE,
            payload=payload,
        )
