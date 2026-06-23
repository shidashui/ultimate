"""WakeWord — two-stage detection: Silero VAD pre-filter → Whisper confirm."""
from __future__ import annotations

import logging

import numpy as np

from config.configs import get_config
from platforms.voice.protocols import WakeWordProtocol, AudioIOProtocol, STTProtocol

logger = logging.getLogger(__name__)


class TwoStageWakeWord(WakeWordProtocol):
    """Two-stage wake word detection.

    Stage 1: Silero VAD endpoint detection identifies candidate speech.
    Stage 2: Whisper ASR transcribes candidate → substring match against wake word.
    """

    def __init__(
        self,
        audio_io: AudioIOProtocol,
        stt: STTProtocol,
        wake_word: str | None = None,
    ):
        cfg = get_config().voice
        self._audio = audio_io
        self._stt = stt
        self._wake_word = wake_word or cfg.wake_word

    async def wait_for_wake(self) -> str | None:
        """Block until wake word detected, then record and return command text."""
        logger.info("Waiting for wake word '%s'...", self._wake_word)
        print(f"\U0001f4a4 等待唤醒词「{self._wake_word}」…", flush=True)

        while True:
            audio = await self._audio.record_utterance()
            if audio is None:
                continue

            text = await self._stt.transcribe(audio)
            if self._wake_word in text.strip():
                logger.info("Wake word detected: %s", text.strip())
                print("✅ 已唤醒，请说指令…", flush=True)
                return await self.record_command()

    async def record_command(self) -> str | None:
        """Record and transcribe command utterance."""
        audio = await self._audio.record_utterance()
        if audio is None:
            return None

        text = (await self._stt.transcribe(audio)).strip()
        if text:
            logger.info("STT: %s", text)
        return text or None
