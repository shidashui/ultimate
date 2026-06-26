"""WakeWord — two-stage detection: Silero VAD pre-filter → Whisper confirm."""
from __future__ import annotations

import logging
from typing import Callable, Awaitable

import numpy as np

from config.configs import get_config
from platforms.voice.protocols import WakeWordProtocol, AudioIOProtocol, STTProtocol

logger = logging.getLogger(__name__)

# Minimum meaningful command length after stripping wake word
MIN_COMMAND_CHARS = 2
# Shorter timeout for command recording (user already woke up)
COMMAND_RECORD_SECS = 8


class TwoStageWakeWord(WakeWordProtocol):
    """Two-stage wake word detection.

    Stage 1: Silero VAD endpoint detection identifies candidate speech.
    Stage 2: Whisper ASR transcribes candidate → substring match against wake word.
    Smart command separation extracts command from the same transcription
    when user says "wake_word + command" in one breath.
    """

    def __init__(
        self,
        audio_io: AudioIOProtocol,
        stt: STTProtocol,
        wake_word: str | None = None,
        status_callback: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        cfg = get_config().voice
        self._audio = audio_io
        self._stt = stt
        self._wake_word = wake_word or cfg.wake_word
        self._status = status_callback

    async def _notify(self, stage: str, detail: str = "") -> None:
        if self._status:
            try:
                await self._status(stage, detail)
            except Exception:
                logger.debug("status callback error", exc_info=True)

    async def wait_for_wake(self) -> str | None:
        """Block until wake word detected, then return command text.

        Smart separation: if user says "wake_word + command" in one breath,
        extract command from the same transcription (no second STT call).
        Falls back to separate command recording if only wake word detected.
        """
        logger.info("Waiting for wake word '%s'...", self._wake_word)
        await self._notify("listening", f"等待唤醒词「{self._wake_word}」…")

        while True:
            audio = await self._audio.record_utterance()
            if audio is None:
                continue

            text = await self._stt.transcribe(audio)
            if not text:
                continue

            # Find wake word position
            idx = text.find(self._wake_word)
            if idx < 0:
                continue

            logger.info("Wake word detected: %s", text.strip())

            # Extract command after wake word
            command = text[idx + len(self._wake_word):].strip()
            # Remove leading punctuation from command
            command = command.lstrip("，。！？、,.!? ")

            if len(command) >= MIN_COMMAND_CHARS:
                logger.info("Smart command extracted: %s", command)
                return command

            # Only wake word detected — need separate command recording
            await self._notify("listening", "已唤醒，请说指令…")
            return await self.record_command()

    async def record_command(self) -> str | None:
        """Record and transcribe command utterance (8s timeout)."""
        audio = await self._audio.record_utterance(max_secs=COMMAND_RECORD_SECS)
        if audio is None:
            return None

        text = (await self._stt.transcribe(audio)).strip()
        if text:
            logger.info("STT: %s", text)
        return text or None
