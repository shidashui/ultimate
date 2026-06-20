"""
SILK audio transcoding utilities
"""

import logging
import io
from typing import Optional

logger = logging.getLogger(__name__)

# Default sample rate for Weixin voice messages
SILK_SAMPLE_RATE = 24000


def pcm_bytes_to_wav(pcm_data: bytes, sample_rate: int = SILK_SAMPLE_RATE) -> bytes:
    """
    Wrap raw pcm_s16le bytes in a WAV container.
    Mono channel, 16-bit signed little-endian.

    Args:
        pcm_data: Raw PCM data (16-bit signed little-endian, mono)
        sample_rate: Sample rate in Hz

    Returns:
        WAV format bytes
    """
    pcm_len = len(pcm_data)
    total_size = 44 + pcm_len

    # Build WAV header
    wav_header = bytearray(44)

    # RIFF chunk
    wav_header[0:4] = b'RIFF'
    wav_header[4:8] = (total_size - 8).to_bytes(4, 'little')
    wav_header[8:12] = b'WAVE'

    # fmt chunk
    wav_header[12:16] = b'fmt '
    wav_header[16:20] = (16).to_bytes(4, 'little')  # fmt chunk size
    wav_header[20:22] = (1).to_bytes(2, 'little')   # PCM format
    wav_header[22:24] = (1).to_bytes(2, 'little')   # mono
    wav_header[24:28] = sample_rate.to_bytes(4, 'little')
    wav_header[28:32] = (sample_rate * 2).to_bytes(4, 'little')  # byte rate (mono 16-bit)
    wav_header[32:34] = (2).to_bytes(2, 'little')   # block align
    wav_header[34:36] = (16).to_bytes(2, 'little')  # bits per sample

    # data chunk
    wav_header[36:40] = b'data'
    wav_header[40:44] = pcm_len.to_bytes(4, 'little')

    return bytes(wav_header) + pcm_data


def silk_to_pcm(silk_data: bytes, sample_rate: int = SILK_SAMPLE_RATE) -> Optional[bytes]:
    """
    Decode SILK data to PCM using pysilk.

    Args:
        silk_data: Raw SILK encoded data
        sample_rate: Expected sample rate

    Returns:
        PCM data (16-bit signed little-endian) or None if decoding fails
    """
    try:
        import pysilk
    except ImportError:
        logger.warning("silk_to_pcm: pysilk module not available")
        return None

    # Check for SILK header
    if not silk_data.startswith(b"\x02#!SILK_V3"):
        logger.warning("silk_to_pcm: data does not have SILK_V3 header")
        return None

    try:
        # Use BytesIO for in-memory decoding
        silk_input = io.BytesIO(silk_data)
        pcm_output = io.BytesIO()

        pysilk.decode(silk_input, pcm_output, sample_rate)

        pcm_data = pcm_output.getvalue()

        logger.debug(f"silk_to_pcm: decoded {len(silk_data)} bytes -> {len(pcm_data)} bytes PCM")
        return pcm_data

    except Exception as e:
        logger.warning(f"silk_to_pcm: pysilk decode failed: {e}")
        return None


def silk_to_wav(silk_data: bytes, sample_rate: int = SILK_SAMPLE_RATE) -> Optional[bytes]:
    """
    Transcode SILK audio to WAV format.

    Args:
        silk_data: Raw SILK encoded data
        sample_rate: Sample rate (default 24000 Hz for Weixin)

    Returns:
        WAV format bytes or None if transcoding fails.
        Callers should fall back to saving raw SILK when None is returned.
    """
    try:
        logger.debug(f"silk_to_wav: decoding {len(silk_data)} bytes of SILK")
        pcm_data = silk_to_pcm(silk_data, sample_rate)

        if pcm_data is None:
            return None

        wav_data = pcm_bytes_to_wav(pcm_data, sample_rate)
        logger.debug(f"silk_to_wav: WAV size={len(wav_data)} duration_ms={len(pcm_data) // 2 * 1000 // sample_rate}")
        return wav_data

    except Exception as e:
        logger.warning(f"silk_to_wav: transcode failed, will use raw silk err={e}")
        return None
