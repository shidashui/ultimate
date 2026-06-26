"""TTS — async text-to-speech via Microsoft Edge TTS."""
from __future__ import annotations

import asyncio
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
        """Synthesize text to MP3 bytes with automatic retry.

        Retries on network/synthesis failure with exponential backoff.
        Raises TTSException if all attempts fail.
        """
        if not text.strip():
            return b""

        max_retries = get_config().voice.tts_retry_count
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
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
                last_error = e
                if attempt < max_retries:
                    wait = 2 ** attempt  # 1s, 2s, 4s, ...
                    logger.warning(
                        "TTS attempt %d/%d failed, retrying in %ds: %s",
                        attempt + 1, max_retries + 1, wait, e,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "TTS all %d attempts failed: %s", max_retries + 1, e
                    )

        raise TTSException(
            f"TTS synthesis failed after {max_retries + 1} attempts: {last_error}"
        ) from last_error
