"""AudioIO — sound device capture/playback with Silero-VAD endpoint detection."""
from __future__ import annotations

import asyncio
import collections
import io
import logging
from typing import Callable, Awaitable

import numpy as np
import sounddevice as sd

from config.configs import get_config
from platforms.voice.protocols import AudioIOProtocol

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE = 16000
FRAME_MS = 32  # Silero requires EXACTLY 512 samples at 16000Hz — no more, no less
FRAME_SIZE = int(DEFAULT_SAMPLE_RATE * FRAME_MS / 1000)  # 512 samples
PADDING_MS = 400
NUM_PADDING = PADDING_MS // FRAME_MS  # ~13 frames


class SileroAudioIO(AudioIOProtocol):
    """Audio I/O with Silero-VAD endpoint detection."""

    def __init__(
        self,
        sample_rate: int | None = None,
        vad_threshold: float | None = None,
        status_callback: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        cfg = get_config().voice
        self.sample_rate = sample_rate or cfg.sample_rate
        self.vad_threshold = vad_threshold or cfg.vad_threshold
        self._vad_model = None  # lazy loaded: (model, utils) tuple
        self._vad_available = True  # set False if warmup fails
        self._status = status_callback

    async def _notify(self, stage: str, detail: str = "") -> None:
        if self._status:
            try:
                await self._status(stage, detail)
            except Exception:
                logger.debug("status callback error", exc_info=True)

    async def warmup_silero(self, timeout: float = 15.0) -> bool:
        """Preload Silero VAD model with timeout. Returns True on success."""
        loop = asyncio.get_event_loop()
        await self._notify("loading", "正在加载语音检测模型…")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._load_silero),
                timeout=timeout,
            )
            await self._notify("loading", "语音检测模型就绪")
            return True
        except asyncio.TimeoutError:
            logger.warning("Silero VAD warmup timed out, falling back to amplitude VAD")
            self._vad_available = False
            await self._notify("loading", "语音检测模型超时，降级到振幅检测")
            return False
        except Exception as e:
            logger.warning("Silero VAD warmup failed: %s, falling back to amplitude VAD", e)
            self._vad_available = False
            await self._notify("loading", "语音检测模型不可用，降级到振幅检测")
            return False

    def _load_silero(self) -> None:
        """Load Silero VAD model (runs in executor)."""
        import torch

        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
        )
        self._vad_model = (model, utils)

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
        """Synchronous recording — Silero VAD if available, amplitude fallback."""
        if self._vad_available and self._vad_model is not None:
            try:
                return self._record_silero_sync(threshold, max_secs)
            except Exception:
                logger.warning("Silero VAD error, falling back to amplitude", exc_info=True)
        return self._record_amplitude_sync(max_secs)

    def _record_silero_sync(self, threshold: float, max_secs: int) -> np.ndarray | None:
        """Silero-based VAD recording."""
        import torch

        model, utils = self._vad_model
        (get_speech_timestamps, _, _, _, _) = utils

        ring = collections.deque(maxlen=NUM_PADDING)
        triggered = False
        pcm_buf: list[np.ndarray] = []  # float32 arrays, one per VAD frame
        max_frame_count = int(max_secs * 1000 / FRAME_MS)
        frame_count = 0

        # Accumulator: blocksize=0 may return chunks ≠ FRAME_SIZE (e.g. 640).
        # Buffer them and feed exactly FRAME_SIZE samples to the Silero model.
        sample_acc = np.array([], dtype=np.float32)

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=0,  # auto: PortAudio picks WASAPI-friendly buffer
        ) as stream:
            while frame_count < max_frame_count:
                raw, _ = stream.read(FRAME_SIZE)
                chunk = (
                    np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                )
                sample_acc = np.concatenate([sample_acc, chunk])

                while len(sample_acc) >= FRAME_SIZE and frame_count < max_frame_count:
                    vad_chunk = sample_acc[:FRAME_SIZE]
                    sample_acc = sample_acc[FRAME_SIZE:]

                    speech_prob = model(
                        torch.from_numpy(vad_chunk), self.sample_rate
                    ).item()
                    is_speech = speech_prob > threshold
                    ring.append(is_speech)

                    if not triggered:
                        pcm_buf.append(vad_chunk)
                        if len(pcm_buf) > NUM_PADDING:
                            pcm_buf.pop(0)
                        if sum(ring) / len(ring) >= 0.75:
                            triggered = True
                            logger.debug(
                                "Silero VAD: speech start (threshold=%.2f)", threshold
                            )
                    else:
                        pcm_buf.append(vad_chunk)
                        if sum(ring) / len(ring) < 0.25:
                            logger.debug("Silero VAD: speech end")
                            break
                    frame_count += 1

                if triggered and sum(ring) / len(ring) < 0.25:
                    break

        if not triggered:
            return None

        audio = np.concatenate(pcm_buf)
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
            blocksize=0,  # auto: PortAudio picks WASAPI-friendly buffer; read(512) accumulates
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
        import soundfile as sf

        audio, sr = sf.read(io.BytesIO(audio_bytes))
        sd.play(audio, sr)
        sd.wait()
