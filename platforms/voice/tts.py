"""TTS — async text-to-speech via Microsoft Edge TTS."""
from __future__ import annotations

import io
import logging

from config.configs import get_config
from platforms.voice.protocols import TTSProtocol

logger = logging.getLogger(__name__)


class TTSException(Exception):
    """Raised when TTS synthesis fails."""


class EdgeTTS(TTSProtocol):
    """Async TTS using Microsoft Edge TTS (free, high-quality Chinese)."""

    def __init__(self, voice: str | None = None):
        cfg = get_config().voice
        self.voice = voice or cfg.tts_voice

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to MP3 bytes.

        Raises TTSException on network or synthesis failure.
        """
        if not text.strip():
            return b""

        try:
            from edge_tts import Communicate

            communicate = Communicate(text, self.voice)
            mp3_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data.write(chunk["data"])
            result = mp3_data.getvalue()
            if not result:
                logger.warning("TTS produced empty audio for: %s", text[:50])
            return result
        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)
            raise TTSException(f"TTS synthesis failed: {e}") from e
