"""Voice platform — modular, config-driven speech interface."""

from platforms.voice.protocols import (
    AudioIOProtocol,
    STTProtocol,
    TTSProtocol,
    WakeWordProtocol,
)
from platforms.voice.platform import VoicePlatform

__all__ = [
    "AudioIOProtocol",
    "STTProtocol",
    "TTSProtocol",
    "WakeWordProtocol",
    "VoicePlatform",
]
