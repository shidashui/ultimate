"""STT — speech-to-text via faster-whisper with in-memory pipeline."""
from __future__ import annotations

import asyncio
import io
import logging
from pathlib import Path
from typing import Callable, Awaitable

import numpy as np
from scipy.io.wavfile import write as wav_write

from config.configs import get_config
from platforms.voice.protocols import STTProtocol

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000

# Local model directory: models/whisper/<model_size>/
LOCAL_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "whisper"


def _resolve_model_path(model_size: str) -> str:
    """Return local model path if available, otherwise model_size name."""
    local_path = LOCAL_MODEL_DIR / model_size
    marker = local_path / ".model_ready"
    if local_path.is_dir() and marker.is_file():
        logger.info("Using local Whisper model: %s", local_path)
        return str(local_path)
    logger.info("Whisper model from HuggingFace (cache): %s", model_size)
    return model_size


class WhisperSTT(STTProtocol):
    """Speech-to-text using faster-whisper (local, offline)."""

    def __init__(
        self,
        model_size: str | None = None,
        status_callback: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        cfg = get_config().voice
        self.model_size = model_size or cfg.model
        self.beam_size = cfg.stt_beam_size
        self.vad_filter = cfg.stt_vad_filter
        self._status = status_callback
        self._model = None  # lazy loaded

    async def _notify(self, stage: str, detail: str = "") -> None:
        if self._status:
            try:
                await self._status(stage, detail)
            except Exception:
                logger.debug("status callback error", exc_info=True)

    def _get_model(self):
        """Lazy-load WhisperModel (local path preferred, fallback HuggingFace)."""
        if self._model is None:
            from faster_whisper import WhisperModel

            model_path = _resolve_model_path(self.model_size)
            self._model = WhisperModel(
                model_path,
                device="cpu",
                compute_type="int8",
            )
        return self._model

    async def warmup(self, timeout: float = 60.0) -> bool:
        """Preload WhisperModel with timeout. Returns True on success."""
        loop = asyncio.get_event_loop()
        await self._notify("loading", f"正在加载Whisper模型({self.model_size})…")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._get_model),
                timeout=timeout,
            )
            await self._notify("loading", "Whisper模型就绪")
            return True
        except asyncio.TimeoutError:
            logger.error("Whisper model warmup timed out after %.0fs", timeout)
            await self._notify("error", "Whisper模型加载超时")
            return False
        except Exception as e:
            logger.error("Whisper model warmup failed: %s", e)
            await self._notify("error", f"Whisper模型加载失败: {e}")
            return False

    async def transcribe(self, audio: np.ndarray, language: str = "zh") -> str:
        """Transcribe audio to text using in-memory WAV buffer."""
        loop = asyncio.get_event_loop()
        await self._notify("transcribing", "语音识别中…")
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
            vad_filter=self.vad_filter,
            initial_prompt="以下是普通话日常对话。",
            beam_size=self.beam_size,
        )
        return "".join(s.text for s in segments)
