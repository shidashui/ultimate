"""VoicePlatform — orchestrator assembling AudioIO/STT/TTS/WakeWord modules."""
from __future__ import annotations

import asyncio
import logging

from gateway import BasePlatform, Message, Reply
from config.configs import get_config
from platforms.voice.audio import SileroAudioIO
from platforms.voice.stt import WhisperSTT
from platforms.voice.tts import EdgeTTS, TTSException
from platforms.voice.wake import TwoStageWakeWord

logger = logging.getLogger(__name__)

VOICE_USER_ID = "voice_user"
VOICE_SESSION_ID = "voice_default"


class VoicePlatform(BasePlatform):
    """Modular voice platform — config-driven, dependency-injected components."""

    platform_name = "voice"
    channel = "voice"

    def __init__(self, wake_word: str | None = None, whisper_model: str | None = None):
        cfg = get_config().voice
        self._wake_word = wake_word or cfg.wake_word
        self._model_size = whisper_model or cfg.model

        # Components (created at init, started in start())
        self._audio = SileroAudioIO()
        self._stt = WhisperSTT(model_size=self._model_size)
        self._tts = EdgeTTS()
        self._wake: TwoStageWakeWord | None = None

        self._queue: asyncio.Queue = asyncio.Queue()
        self._speaking: bool = False

    # ── Lifecycle ───────────────────────────────────────

    async def start(self) -> None:
        logger.info(
            "voice platform starting (model=%s, wake_word=%s, tts=%s)",
            self._model_size, self._wake_word, get_config().voice.tts_voice,
        )
        # Warm up STT model
        _ = self._stt._get_model()
        logger.info("Whisper model '%s' loaded", self._model_size)

        self._wake = TwoStageWakeWord(
            audio_io=self._audio,
            stt=self._stt,
            wake_word=self._wake_word,
        )
        asyncio.create_task(self._listen_loop())

    async def stop(self) -> None:
        logger.info("voice platform stopped")

    # ── BasePlatform interface ───────────────────────────

    async def receive(self) -> Message:
        return await self._queue.get()

    async def send(self, reply: Reply) -> None:
        text = reply.content.strip()
        if not text:
            return
        try:
            await self._speak(text)
        except TTSException as e:
            logger.error("TTS send error: %s", e)

    # ── Listen loop ─────────────────────────────────────

    async def _listen_loop(self) -> None:
        logger.info("listen loop started")

        while True:
            try:
                # Wait for TTS to finish before listening
                while self._speaking:
                    await asyncio.sleep(0.05)

                # Wake word → record command
                text = await self._wake.wait_for_wake()
                if text:
                    await self._queue.put(Message(
                        platform=self.platform_name,
                        user_id=VOICE_USER_ID,
                        session_id=VOICE_SESSION_ID,
                        content=text,
                    ))

            except Exception as e:
                logger.error("Listen loop error: %s", e)
                await asyncio.sleep(1)

    # ── TTS ─────────────────────────────────────────────

    async def _speak(self, text: str) -> None:
        self._speaking = True
        try:
            mp3_bytes = await self._tts.synthesize(text)
            if mp3_bytes:
                await self._audio.play(mp3_bytes)
        finally:
            self._speaking = False
