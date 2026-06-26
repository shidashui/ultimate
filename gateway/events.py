# gateway/events.py
"""Tauri ↔ Python WebSocket 事件类型定义。"""

# ── 后端 → 前端 ──
EVENT_WAKE = "wake"
EVENT_STT = "stt"
EVENT_THINKING = "thinking"
EVENT_TEXT_CHUNK = "text_chunk"
EVENT_DATA = "data"
EVENT_AMPLITUDE = "amplitude"
EVENT_TTS_START = "tts_start"
EVENT_TTS_END = "tts_end"
EVENT_IDLE = "idle"
EVENT_ERROR = "error"
EVENT_STATUS = "status"

# ── 前端 → 后端 ──
EVENT_INPUT = "input"
EVENT_CLOSE = "close"
EVENT_HELLO = "hello"


def wake_event() -> dict:
    return {"event": EVENT_WAKE}


def stt_event(text: str) -> dict:
    return {"event": EVENT_STT, "text": text}


def thinking_event() -> dict:
    return {"event": EVENT_THINKING}


def text_chunk_event(text: str) -> dict:
    return {"event": EVENT_TEXT_CHUNK, "text": text}


def data_table_event(columns: list[str], rows: list[list]) -> dict:
    return {"event": EVENT_DATA, "type": "table", "columns": columns, "rows": rows}


def amplitude_event(rms: float) -> dict:
    return {"event": EVENT_AMPLITUDE, "rms": rms}


def tts_start_event() -> dict:
    return {"event": EVENT_TTS_START}


def tts_end_event() -> dict:
    return {"event": EVENT_TTS_END}


def idle_event() -> dict:
    return {"event": EVENT_IDLE}


def error_event(reason: str) -> dict:
    return {"event": EVENT_ERROR, "reason": reason}


def status_event(stage: str, detail: str = "") -> dict:
    """Voice platform status event for GUI progress feedback.

    Stages: loading, listening, transcribing, thinking, speaking, idle, error
    """
    return {"event": EVENT_STATUS, "stage": stage, "detail": detail}
