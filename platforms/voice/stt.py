"""STT — speech-to-text via faster-whisper with in-memory pipeline."""
from __future__ import annotations

import asyncio
import io
import logging

import numpy as np
from scipy.io.wavfile import write as wav_write

from config.configs import get_config
from platforms.voice.protocols import STTProtocol

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


class WhisperSTT(STTProtocol):
    """Speech-to-text using faster-whisper (local, offline)."""

    def __init__(self, model_size: str | None = None):
        cfg = get_config().voice
        self.model_size = model_size or cfg.model
        self._model = None  # lazy loaded

    def _get_model(self):
        """Lazy-load WhisperModel."""
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
        return self._model

    async def transcribe(self, audio: np.ndarray, language: str = "zh") -> str:
        """Transcribe audio to text using in-memory WAV buffer."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, audio, language)

    def _transcribe_sync(self, audio: np.ndarray, language: str) -> str:
        """Synchronous transcription (runs in executor). No temp files."""
        model = self._get_model()

        # Write to in-memory BytesIO instead of temp file
        buf = io.BytesIO()
        wav_write(buf, SAMPLE_RATE, (audio * 32768).astype(np.int16))
        buf.seek(0)

        segments, _ = model.transcribe(
            buf,
            language=language,
            vad_filter=True,
            initial_prompt="以下是普通话日常对话。",
            beam_size=5,
        )
        return "".join(s.text for s in segments)
