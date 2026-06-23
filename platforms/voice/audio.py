"""AudioIO — sound device capture/playback with Silero-VAD endpoint detection."""
from __future__ import annotations

import asyncio
import collections
import io
import logging

import numpy as np
import sounddevice as sd

from config.configs import get_config
from platforms.voice.protocols import AudioIOProtocol

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16000
FRAME_MS = 30  # Silero works best with 30ms frames
FRAME_SIZE = int(DEFAULT_SAMPLE_RATE * FRAME_MS / 1000)  # 480 samples
PADDING_MS = 400
NUM_PADDING = PADDING_MS // FRAME_MS  # ~13 frames


class SileroAudioIO(AudioIOProtocol):
    """Audio I/O with Silero-VAD endpoint detection."""

    def __init__(self, sample_rate: int | None = None, vad_threshold: float | None = None):
        cfg = get_config().voice
        self.sample_rate = sample_rate or cfg.sample_rate
        self.vad_threshold = vad_threshold or cfg.vad_threshold
        self._vad_model = None  # lazy loaded

    async def record_utterance(
        self, vad_threshold: float = 0.5, max_secs: int = 30
    ) -> np.ndarray | None:
        """Record with VAD-driven endpoint detection."""
        loop = asyncio.get_event_loop()
        threshold = vad_threshold if vad_threshold != 0.5 else self.vad_threshold
        return await loop.run_in_executor(
            None, self._record_sync, threshold, max_secs
        )

    def _record_sync(self, threshold: float, max_secs: int) -> np.ndarray | None:
        """Synchronous recording with Silero VAD (runs in executor)."""
        try:
            import torch

            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
            )
            (get_speech_timestamps, _, _, _, _) = utils
        except Exception:
            # Fallback: use amplitude-based VAD
            return self._record_amplitude_sync(max_secs)

        ring = collections.deque(maxlen=NUM_PADDING)
        triggered = False
        pcm_buf: list[bytes] = []
        max_frames = int(max_secs * 1000 / FRAME_MS)

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SIZE,
        ) as stream:
            for _ in range(max_frames):
                raw, _ = stream.read(FRAME_SIZE)
                pcm = bytes(raw)
                audio_chunk = (
                    np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                )
                speech_prob = model(
                    torch.from_numpy(audio_chunk), self.sample_rate
                ).item()
                is_speech = speech_prob > threshold
                ring.append(is_speech)

                if not triggered:
                    pcm_buf.append(pcm)
                    if len(pcm_buf) > NUM_PADDING:
                        pcm_buf.pop(0)
                    if sum(ring) / len(ring) >= 0.75:
                        triggered = True
                        logger.debug("VAD: speech start (threshold=%.2f)", threshold)
                else:
                    pcm_buf.append(pcm)
                    if sum(ring) / len(ring) < 0.25:
                        logger.debug("VAD: speech end")
                        break

        if not triggered:
            return None

        raw_bytes = b"".join(pcm_buf)
        audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return audio if len(audio) > self.sample_rate * 0.3 else None

    def _record_amplitude_sync(self, max_secs: int) -> np.ndarray | None:
        """Fallback: amplitude-based detection when Silero unavailable."""
        ring = collections.deque(maxlen=NUM_PADDING)
        triggered = False
        pcm_buf: list[bytes] = []
        max_frames = int(max_secs * 1000 / FRAME_MS)

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=FRAME_SIZE,
        ) as stream:
            for _ in range(max_frames):
                raw, _ = stream.read(FRAME_SIZE)
                pcm = bytes(raw)
                arr = np.frombuffer(raw, dtype=np.int16)
                amplitude = np.abs(arr).mean()
                is_speech = amplitude > 500  # empirical threshold
                ring.append(is_speech)

                if not triggered:
                    pcm_buf.append(pcm)
                    if len(pcm_buf) > NUM_PADDING:
                        pcm_buf.pop(0)
                    if sum(ring) / len(ring) >= 0.75:
                        triggered = True
                else:
                    pcm_buf.append(pcm)
                    if sum(ring) / len(ring) < 0.25:
                        break

        if not triggered:
            return None

        raw_bytes = b"".join(pcm_buf)
        audio = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        return audio if len(audio) > self.sample_rate * 0.3 else None

    async def play(self, audio_bytes: bytes, sample_rate: int = 24000) -> None:
        """Play MP3 audio bytes through speakers."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._play_sync, audio_bytes, sample_rate)

    @staticmethod
    def _play_sync(audio_bytes: bytes, sample_rate: int) -> None:
        try:
            import soundfile as sf

            audio, sr = sf.read(io.BytesIO(audio_bytes))
            sd.play(audio, sr)
            sd.wait()
        except Exception as e:
            logger.error(f"Playback error: {e}")
