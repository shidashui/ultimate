"""
perception/event.py
统一事件结构体 —— 所有感知模块的输出格式
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal
import time


EventModality = Literal["video", "audio", "fused"]


@dataclass
class PerceptionEvent:
    """
    结构化感知事件

    type        : 事件类型，格式 "<模块>_<动作>"，例如 "object_appeared"
    modality    : 来源模态
    timestamp   : 事件产生时刻（秒，Unix time）
    confidence  : 置信度 0~1，供注意力层过滤用
    source      : 产生事件的模块名，便于调试
    payload     : 模块自定义字段，见各模块文档
    """
    type: str
    modality: EventModality
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    source: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    # 支持优先级队列，置信度越高越先处理
    def __lt__(self, other: "PerceptionEvent") -> bool:
        return self.confidence > other.confidence

    def __repr__(self) -> str:
        ts = f"{self.timestamp:.3f}"
        return (f"[{ts}] {self.modality}/{self.type}"
                f" conf={self.confidence:.2f} {self.payload}")


# ── 常用 type 常量，避免拼写错误 ──────────────────────────────────────
class VideoEventType:
    # YOLO 目标
    OBJECT_APPEARED  = "object_appeared"   # 新 track_id 出现
    OBJECT_VANISHED  = "object_vanished"   # track_id 消失
    OBJECT_PRESENT   = "object_present"    # 持续存在（低频心跳）

    # 运动
    MOTION_DETECTED  = "motion_detected"   # 背景减除检测到运动
    SCENE_CHANGE     = "scene_change"      # 画面整体突变

    # 姿态 / 手势
    POSE_DETECTED    = "pose_detected"     # 检测到人体关键点
    GESTURE          = "gesture"           # 具体手势事件

class AudioEventType:
    SOUND_ONSET  = "sound_onset"
    SILENCE      = "silence"
    AUDIO_SPIKE  = "audio_spike"
