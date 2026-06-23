"""Protocol interfaces for voice platform modules.

All modules use typing.Protocol — zero runtime overhead, duck-typing compatible.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class AudioIOProtocol(Protocol):
    """Audio capture and playback."""

    async def record_utterance(
        self, vad_threshold: float = 0.5, max_secs: int = 30
    ) -> np.ndarray | None:
        """Record user utterance with VAD-driven endpoint detection.

        Returns float32 numpy array (16000 Hz mono), or None if no speech detected.
        """
        ...

    async def play(self, audio_bytes: bytes, sample_rate: int = 24000) -> None:
        """Play audio bytes through speaker (non-blocking for event loop)."""
        ...


class STTProtocol(Protocol):
    """Speech-to-text transcription."""

    async def transcribe(self, audio: np.ndarray, language: str = "zh") -> str:
        """Transcribe audio array to text.

        Args:
            audio: float32 numpy array, 16000 Hz mono.
            language: ISO language code.

        Returns transcribed text string.
        """
        ...


class TTSProtocol(Protocol):
    """Text-to-speech synthesis."""

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to MP3 audio bytes.

        Returns MP3-encoded audio bytes, or empty bytes on failure.
        """
        ...


class WakeWordProtocol(Protocol):
    """Wake word detection."""

    async def wait_for_wake(self) -> str | None:
        """Block until wake word is detected.

        Returns the transcribed command text after wake word, or None on timeout/error.
        """
        ...

    async def record_command(self) -> str | None:
        """Record and transcribe a command utterance after wake word.

        Returns transcribed text, or None if no speech.
        """
        ...
