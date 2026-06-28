"""TTS — async text-to-speech via Microsoft Edge TTS."""
from __future__ import annotations

import asyncio
import io
import logging
import re

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

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Strip common markdown syntax, returning plain readable text."""
        # Code blocks (fenced)
        text = re.sub(r"```[\s\S]*?```", "", text)
        # Inline code
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Images (remove entirely — alt text is often not meaningful spoken)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        # Links: keep text, drop URL
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        # Bold/italic markers
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"\*([^*\n]+?)\*", r"\1", text)
        text = re.sub(r"_([^_\n]+?)_", r"\1", text)
        # Strikethrough
        text = re.sub(r"~~(.+?)~~", r"\1", text)
        # Headings: drop # markers, keep heading text
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
        # Horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Block quotes
        text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
        # Unordered list markers (keep content, drop marker)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
        # Ordered list markers (keep content, drop number)
        text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Strip leading/trailing whitespace
        return text.strip()

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

                communicate = Communicate(self._strip_markdown(text), self.voice)
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
