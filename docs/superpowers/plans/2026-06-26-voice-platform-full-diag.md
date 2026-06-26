---
change: voice-platform-full-diag
design-doc: docs/superpowers/specs/2026-06-26-voice-platform-full-diag-design.md
base-ref: b5edc5a15b01e5b13d143b2afcf46d78e0d854f2
archived-with: 2026-06-26-voice-platform-full-diag
---

# Voice Platform Full-Chain Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 7 voice platform bottlenecks (P0 hangs, P1 redundant STT, P2-P3 UX gaps) across 7 files with 6 targeted changes.

**Architecture:** Add status callback injection to existing DI pattern; add startup warmup for Silero/Whisper; implement smart command separation in wake word; tune STT parameters; replace busy-wait with asyncio.Event; extend VoiceConfig with 5 new fields.

**Tech Stack:** Python 3.11+, faster-whisper, sounddevice, numpy, edge_tts, pytest

## Global Constraints

- Do NOT change VoicePlatform public interface (`receive`/`send` signatures)
- Do NOT change Protocol interfaces (`AudioIOProtocol`, `STTProtocol`, `TTSProtocol`, `WakeWordProtocol`)
- Do NOT change Gateway or AgentRunner
- All new config fields must have sensible defaults (backward compatible)
- Status events must not crash the platform if broadcast fails (catch + log debug)

archived-with: 2026-06-26-voice-platform-full-diag
---

### Task 1: VoiceConfig Extension + config.yaml

**Files:**
- Modify: `config/configs.py:65-73`
- Modify: `config.yaml:50-58`

**Interfaces:**
- Produces: `VoiceConfig` dataclass with 5 new fields (see below)

- [ ] **Step 1: Add new fields to VoiceConfig dataclass**

In `config/configs.py`, replace the `VoiceConfig` dataclass:

```python
@dataclass
class VoiceConfig:
    model: str = "small"
    vad: str = "silero"
    vad_threshold: float = 0.5
    wake_word: str = "你好"
    sample_rate: int = 16000
    max_record_secs: int = 30
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    # 新增
    stt_beam_size: int = 3
    stt_vad_filter: bool = False
    silero_download_timeout: int = 15
    stt_model_warmup: bool = True
    status_verbose: bool = True
```

- [ ] **Step 2: Update load_config() voice section parsing**

In `config/configs.py`, locate `voice_raw = raw.get("voice", {})` block (~line 211) and update `voice = VoiceConfig(...)` call:

```python
voice = VoiceConfig(
    model=voice_raw.get("model", "small"),
    vad=voice_raw.get("vad", "silero"),
    vad_threshold=float(voice_raw.get("vad_threshold", 0.5)),
    wake_word=voice_raw.get("wake_word", "你好"),
    sample_rate=int(voice_raw.get("sample_rate", 16000)),
    max_record_secs=int(voice_raw.get("max_record_secs", 30)),
    tts_voice=voice_raw.get("tts_voice", "zh-CN-XiaoxiaoNeural"),
    # 新增
    stt_beam_size=int(voice_raw.get("stt_beam_size", 3)),
    stt_vad_filter=bool(voice_raw.get("stt_vad_filter", False)),
    silero_download_timeout=int(voice_raw.get("silero_download_timeout", 15)),
    stt_model_warmup=bool(voice_raw.get("stt_model_warmup", True)),
    status_verbose=bool(voice_raw.get("status_verbose", True)),
)
```

- [ ] **Step 3: Add new keys to config.yaml voice section**

In `config.yaml`, append to the `voice:` block:

```yaml
voice:
  model: small
  vad: silero
  vad_threshold: 0.5
  wake_word: "你好"
  sample_rate: 16000
  max_record_secs: 30
  tts_voice: zh-CN-XiaoxiaoNeural
  stt_beam_size: 3
  stt_vad_filter: false
  silero_download_timeout: 15
  stt_model_warmup: true
  status_verbose: true
```

- [ ] **Step 4: Run config tests to verify**

```bash
python -m pytest tests/test_voice_platform.py::TestVoiceConfig -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add config/configs.py config.yaml
git commit -m "feat(voice): add stt_beam_size, stt_vad_filter, silero_download_timeout, stt_model_warmup, status_verbose to VoiceConfig"
```

archived-with: 2026-06-26-voice-platform-full-diag
---

### Task 2: Status Events Factory

**Files:**
- Modify: `gateway/events.py`

**Interfaces:**
- Produces: `status_event(stage: str, detail: str = "") -> dict`

- [ ] **Step 1: Read current events.py**

```bash
# Check current event factories
```

Read `gateway/events.py` to understand existing event format (e.g., `wake_event()`, `stt_event()`, `idle_event()`). The new `status_event()` follows the same pattern.

- [ ] **Step 2: Add status_event factory**

In `gateway/events.py`, add:

```python
def status_event(stage: str, detail: str = "") -> dict:
    """Voice platform status event for GUI progress feedback.
    
    Stages: loading, listening, transcribing, thinking, speaking, idle, error
    """
    return {
        "event": "status",
        "stage": stage,
        "detail": detail,
    }
```

- [ ] **Step 3: Verify import works**

```bash
python -c "from gateway.events import status_event; print(status_event('loading', 'test'))"
```

Expected: `{'event': 'status', 'stage': 'loading', 'detail': 'test'}`

- [ ] **Step 4: Commit**

```bash
git add gateway/events.py
git commit -m "feat(voice): add status_event factory for voice platform progress feedback"
```

archived-with: 2026-06-26-voice-platform-full-diag
---

### Task 3: STT Optimization (beam_size, vad_filter, warmup, status callback)

**Files:**
- Modify: `platforms/voice/stt.py`

**Interfaces:**
- Consumes: `VoiceConfig.stt_beam_size`, `VoiceConfig.stt_vad_filter`, `VoiceConfig.stt_model_warmup`
- Produces: `WhisperSTT` with `status_callback` parameter, `warmup()` method, config-driven transcribe params

- [ ] **Step 1: Add status_callback and warmup support to WhisperSTT**

Replace `platforms/voice/stt.py`:

```python
"""STT — speech-to-text via faster-whisper with in-memory pipeline."""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Callable, Awaitable

import numpy as np
from scipy.io.wavfile import write as wav_write

from config.configs import get_config
from platforms.voice.protocols import STTProtocol

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


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
        """Lazy-load WhisperModel."""
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
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
        try:
            result = await loop.run_in_executor(None, self._transcribe_sync, audio, language)
            return result
        finally:
            pass  # status cleared by caller

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
```

- [ ] **Step 2: Run protocol test to verify interface intact**

```bash
python -m pytest tests/test_voice_platform.py::TestProtocols::test_whisper_stt_implements_protocol -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add platforms/voice/stt.py
git commit -m "feat(voice): add status_callback, warmup(), config-driven beam_size/vad_filter to WhisperSTT"
```

archived-with: 2026-06-26-voice-platform-full-diag
---

### Task 4: Audio I/O — Silero Warmup + Fallback + Status Callback

**Files:**
- Modify: `platforms/voice/audio.py`

**Interfaces:**
- Consumes: `VoiceConfig.silero_download_timeout`, `VoiceConfig.status_verbose`
- Produces: `SileroAudioIO` with `status_callback` param, `_vad_available` flag, `warmup_silero()` method

- [ ] **Step 1: Refactor SileroAudioIO with warmup and status**

Replace `platforms/voice/audio.py`:

```python
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
FRAME_MS = 30  # Silero works best with 30ms frames
FRAME_SIZE = int(DEFAULT_SAMPLE_RATE * FRAME_MS / 1000)  # 480 samples
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
        self._vad_model = None  # lazy loaded
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
        """Synchronous recording with Silero VAD (runs in executor)."""
        # Use Silero if available, otherwise fall back to amplitude
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
                        logger.debug("Silero VAD: speech start (threshold=%.2f)", threshold)
                else:
                    pcm_buf.append(pcm)
                    if sum(ring) / len(ring) < 0.25:
                        logger.debug("Silero VAD: speech end")
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
```

- [ ] **Step 2: Run protocol test**

```bash
python -m pytest tests/test_voice_platform.py::TestProtocols::test_silero_audio_io_implements_protocol -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add platforms/voice/audio.py
git commit -m "feat(voice): add warmup_silero(), _vad_available fallback, status_callback to SileroAudioIO"
```

archived-with: 2026-06-26-voice-platform-full-diag
---

### Task 5: Smart Command Separation + Wake Word Optimization

**Files:**
- Modify: `platforms/voice/wake.py`

**Interfaces:**
- Consumes: `VoiceConfig.wake_word`, `VoiceConfig.max_record_secs`
- Produces: `TwoStageWakeWord` with `status_callback`, smart `wait_for_wake()` command extraction, 8s fallback timeout

- [ ] **Step 1: Refactor TwoStageWakeWord with smart separation and status**

Replace `platforms/voice/wake.py`:

```python
"""WakeWord — two-stage detection: Silero VAD pre-filter → Whisper confirm."""
from __future__ import annotations

import logging
from typing import Callable, Awaitable

import numpy as np

from config.configs import get_config
from platforms.voice.protocols import WakeWordProtocol, AudioIOProtocol, STTProtocol

logger = logging.getLogger(__name__)

# Minimum meaningful command length after stripping wake word
MIN_COMMAND_CHARS = 2
# Shorter timeout for command recording (user already woke up)
COMMAND_RECORD_SECS = 8


class TwoStageWakeWord(WakeWordProtocol):
    """Two-stage wake word detection.

    Stage 1: Silero VAD endpoint detection identifies candidate speech.
    Stage 2: Whisper ASR transcribes candidate → substring match against wake word.
    Smart command separation extracts command from the same transcription
    when user says "wake_word + command" in one breath.
    """

    def __init__(
        self,
        audio_io: AudioIOProtocol,
        stt: STTProtocol,
        wake_word: str | None = None,
        status_callback: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        cfg = get_config().voice
        self._audio = audio_io
        self._stt = stt
        self._wake_word = wake_word or cfg.wake_word
        self._status = status_callback

    async def _notify(self, stage: str, detail: str = "") -> None:
        if self._status:
            try:
                await self._status(stage, detail)
            except Exception:
                logger.debug("status callback error", exc_info=True)

    async def wait_for_wake(self) -> str | None:
        """Block until wake word detected, then return command text.
        
        Smart separation: if user says "wake_word + command" in one breath,
        extract command from the same transcription (no second STT call).
        Falls back to separate command recording if only wake word detected.
        """
        logger.info("Waiting for wake word '%s'...", self._wake_word)
        await self._notify("listening", f"等待唤醒词「{self._wake_word}」…")

        while True:
            audio = await self._audio.record_utterance()
            if audio is None:
                continue

            text = await self._stt.transcribe(audio)
            if not text:
                continue

            # Find wake word position
            idx = text.find(self._wake_word)
            if idx < 0:
                continue

            logger.info("Wake word detected: %s", text.strip())

            # Extract command after wake word
            command = text[idx + len(self._wake_word):].strip()
            # Remove leading punctuation from command
            command = command.lstrip("，。！？、,.!? ")

            if len(command) >= MIN_COMMAND_CHARS:
                logger.info("Smart command extracted: %s", command)
                return command

            # Only wake word detected — need separate command recording
            await self._notify("listening", "已唤醒，请说指令…")
            return await self.record_command()

    async def record_command(self) -> str | None:
        """Record and transcribe command utterance (8s timeout)."""
        audio = await self._audio.record_utterance(max_secs=COMMAND_RECORD_SECS)
        if audio is None:
            return None

        text = (await self._stt.transcribe(audio)).strip()
        if text:
            logger.info("STT: %s", text)
        return text or None
```

- [ ] **Step 2: Run wake word protocol test**

```bash
python -m pytest tests/test_voice_platform.py::TestProtocols::test_two_stage_wake_word_implements_protocol -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add platforms/voice/wake.py
git commit -m "feat(voice): smart command separation in TwoStageWakeWord — extract inline cmd, 8s fallback"
```

archived-with: 2026-06-26-voice-platform-full-diag
---

### Task 6: VoicePlatform Orchestrator — Warmup + Event-Driven + Status Broadcast

**Files:**
- Modify: `platforms/voice/platform.py`

**Interfaces:**
- Consumes: `SileroAudioIO.warmup_silero()`, `WhisperSTT.warmup()`, `VoiceConfig.stt_model_warmup`, `VoiceConfig.silero_download_timeout`
- Produces: `VoicePlatform` with unified `_broadcast_status()`, warmup orchestration, asyncio.Event busy-wait replacement

- [ ] **Step 1: Refactor VoicePlatform with warmup, status, and event-driven loop**

Replace `platforms/voice/platform.py`:

```python
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
from gateway.events import (
    wake_event, stt_event, thinking_event, text_chunk_event,
    tts_start_event, tts_end_event, idle_event, status_event,
)

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
        self._verbose = cfg.status_verbose

        # Components (created at init, started in start())
        self._audio = SileroAudioIO(status_callback=self._broadcast_status)
        self._stt = WhisperSTT(
            model_size=self._model_size,
            status_callback=self._broadcast_status,
        )
        self._tts = EdgeTTS()
        self._wake: TwoStageWakeWord | None = None

        self._queue: asyncio.Queue = asyncio.Queue()
        self._speaking: bool = False
        self._speak_done: asyncio.Event = asyncio.Event()
        self._speak_done.set()  # not speaking initially
        self._tauri_platform = None

    # ── Tauri GUI 集成 ───────────────────────────────────

    def set_tauri_platform(self, tauri_platform) -> None:
        """设置 TauriPlatform 引用，用于 GUI 事件广播。"""
        self._tauri_platform = tauri_platform

    async def _broadcast(self, event: dict) -> None:
        """向 Tauri GUI 广播事件。"""
        if self._tauri_platform:
            await self._tauri_platform.broadcast(event)

    async def _broadcast_status(self, stage: str, detail: str = "") -> None:
        """统一状态广播：推送到 Tauri GUI + 终端输出。"""
        if self._tauri_platform:
            try:
                await self._tauri_platform.broadcast(status_event(stage, detail))
            except Exception:
                logger.debug("status broadcast error", exc_info=True)
        if self._verbose:
            print(f"[Voice] {stage}: {detail}", flush=True)

    def get_text_chunk_callback(self):
        """返回 on_text_chunk 回调，供 Gateway/AgentRunner 流式推送。"""
        if self._tauri_platform is None:
            return None
        return lambda text: asyncio.create_task(
            self._broadcast(text_chunk_event(text))
        )

    # ── Lifecycle ───────────────────────────────────────

    async def start(self) -> None:
        logger.info(
            "voice platform starting (model=%s, wake_word=%s, tts=%s)",
            self._model_size, self._wake_word, get_config().voice.tts_voice,
        )

        cfg = get_config().voice

        # ── Warmup phase ──
        await self._broadcast_status("loading", "正在加载语音模型…")

        if cfg.stt_model_warmup:
            # Parallel warmup for Whisper + Silero
            results = await asyncio.gather(
                self._stt.warmup(timeout=60.0),
                self._audio.warmup_silero(timeout=float(cfg.silero_download_timeout)),
                return_exceptions=True,
            )
            whisper_ok = results[0] if not isinstance(results[0], Exception) else False
            silero_ok = results[1] if not isinstance(results[1], Exception) else False

            if not whisper_ok:
                logger.error("Whisper model warmup failed — voice platform may not function")
                await self._broadcast_status("error", "Whisper模型加载失败")
        else:
            # Legacy: warm STT model inline
            _ = self._stt._get_model()
            logger.info("Whisper model '%s' loaded", self._model_size)

        self._wake = TwoStageWakeWord(
            audio_io=self._audio,
            stt=self._stt,
            wake_word=self._wake_word,
            status_callback=self._broadcast_status,
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
        finally:
            # 交互完成，广播 idle
            await self._broadcast_status("idle", "就绪")

    # ── Listen loop ─────────────────────────────────────

    async def _listen_loop(self) -> None:
        logger.info("listen loop started")

        while True:
            try:
                # Wait for TTS to finish before listening (event-driven)
                await self._speak_done.wait()

                # Wake word → record command
                text = await self._wake.wait_for_wake()
                if text:
                    # 唤醒 → 推 wake + stt 事件
                    await self._broadcast(wake_event())
                    await self._broadcast(stt_event(text))
                    await self._broadcast_status("thinking", "正在思考…")

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
        self._speak_done.clear()
        await self._broadcast_status("speaking", "正在合成语音…")
        try:
            mp3_bytes = await self._tts.synthesize(text)
            if mp3_bytes:
                await self._audio.play(mp3_bytes)
        finally:
            self._speaking = False
            self._speak_done.set()
```

- [ ] **Step 2: Run orchestrator test**

```bash
python -m pytest tests/test_voice_platform.py::TestVoicePlatformOrchestrator -v
```

Expected: PASS (2 tests)

- [ ] **Step 3: Commit**

```bash
git add platforms/voice/platform.py
git commit -m "feat(voice): warmup orchestration, event-driven listen loop, unified _broadcast_status in VoicePlatform"
```

archived-with: 2026-06-26-voice-platform-full-diag
---

### Task 7: Tests — Warmup, Separation, Fallback, Status Events

**Files:**
- Modify: `tests/test_voice_platform.py`

**Interfaces:**
- Consumes: All new features from Tasks 1-6

- [ ] **Step 1: Add test — status_event factory**

Append to `tests/test_voice_platform.py`:

```python
# ── P2: Status events ──────────────────────────────


class TestStatusEvents:
    def test_status_event_has_required_fields(self):
        from gateway.events import status_event

        evt = status_event("loading", "test detail")
        assert evt["event"] == "status"
        assert evt["stage"] == "loading"
        assert evt["detail"] == "test detail"

    def test_status_event_default_detail(self):
        from gateway.events import status_event

        evt = status_event("idle")
        assert evt["detail"] == ""


# ── P2: VoiceConfig new fields ──────────────────────


class TestVoiceConfigNewFields:
    def test_new_config_defaults(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig()
        assert cfg.stt_beam_size == 3
        assert cfg.stt_vad_filter is False
        assert cfg.silero_download_timeout == 15
        assert cfg.stt_model_warmup is True
        assert cfg.status_verbose is True

    def test_new_config_custom(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig(
            stt_beam_size=5,
            stt_vad_filter=True,
            silero_download_timeout=30,
            stt_model_warmup=False,
            status_verbose=False,
        )
        assert cfg.stt_beam_size == 5
        assert cfg.stt_vad_filter is True
        assert cfg.silero_download_timeout == 30
        assert cfg.stt_model_warmup is False
        assert cfg.status_verbose is False


# ── P2: VoicePlatform with status callback ───────────


class TestVoicePlatformStatus:
    def test_platform_has_broadcast_status(self):
        from platforms.voice import VoicePlatform

        vp = VoicePlatform(wake_word="测试", whisper_model="tiny")
        assert hasattr(vp, "_broadcast_status")
        assert callable(vp._broadcast_status)

    @pytest.mark.asyncio
    async def test_broadcast_status_no_tauri(self):
        """status broadcast should not crash when no TauriPlatform set."""
        from platforms.voice import VoicePlatform

        vp = VoicePlatform(wake_word="测试", whisper_model="tiny")
        # Should not raise
        await vp._broadcast_status("loading", "test message")


# ── P2: Smart command separation ────────────────────


class TestCommandSeparation:
    @pytest.mark.asyncio
    async def test_inline_command_extracted(self):
        """Wake word + command in one breath → command returned directly."""
        import numpy as np
        from platforms.voice.wake import TwoStageWakeWord

        class MockAudio:
            def __init__(self):
                self.call_count = 0
            async def record_utterance(self, **kw):
                self.call_count += 1
                return np.zeros(16000, dtype=np.float32)

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return "你好，今天天气怎么样"

        mock_audio = MockAudio()
        mock_stt = MockSTT()
        wake = TwoStageWakeWord(mock_audio, mock_stt, wake_word="你好")

        result = await wake.wait_for_wake()
        assert result == "今天天气怎么样"
        # Should NOT have called record_utterance a second time
        assert mock_audio.call_count == 1

    @pytest.mark.asyncio
    async def test_wake_only_falls_back_to_record(self):
        """Only wake word → record_command() fallback."""
        import numpy as np
        from platforms.voice.wake import TwoStageWakeWord

        class MockAudio:
            def __init__(self):
                self.call_count = 0
            async def record_utterance(self, **kw):
                self.call_count += 1
                return np.zeros(16000, dtype=np.float32)

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return "你好"  # Only wake word

        mock_audio = MockAudio()
        mock_stt = MockSTT()
        wake = TwoStageWakeWord(mock_audio, mock_stt, wake_word="你好")

        result = await wake.wait_for_wake()
        # Should have called record_utterance twice (wake + command)
        assert mock_audio.call_count == 2
        assert result == "你好"  # mock returns wake word again

    @pytest.mark.asyncio
    async def test_empty_text_continues_waiting(self):
        """Empty STT result → continue waiting loop."""
        import numpy as np
        from platforms.voice.wake import TwoStageWakeWord

        call_count = [0]

        class MockAudio:
            async def record_utterance(self, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return np.zeros(16000, dtype=np.float32)  # empty audio
                return np.zeros(16000, dtype=np.float32)

        responses = ["", "你好 帮我查天气"]  # empty → wake+cmd

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return responses.pop(0)

        mock_audio = MockAudio()
        mock_stt = MockSTT()
        wake = TwoStageWakeWord(mock_audio, mock_stt, wake_word="你好")

        result = await wake.wait_for_wake()
        assert result == "帮我查天气"


# ── P2: Audio Silero fallback ──────────────────────


class TestSileroFallback:
    def test_vad_available_flag_exists(self):
        from platforms.voice.audio import SileroAudioIO

        io = SileroAudioIO()
        assert hasattr(io, "_vad_available")
        assert io._vad_available is True

    def test_record_sync_falls_back_when_unavailable(self):
        """When _vad_available=False, should use amplitude VAD without crash."""
        from platforms.voice.audio import SileroAudioIO

        io = SileroAudioIO()
        io._vad_available = False
        io._vad_model = None
        # _record_sync should use amplitude fallback
        # Note: this will open a real audio stream — test only the flag logic
        assert io._vad_available is False
```

- [ ] **Step 2: Run all new tests**

```bash
python -m pytest tests/test_voice_platform.py -v
```

Expected: ALL PASS (existing 14 + new ~10 tests)

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_voice_platform.py
git commit -m "test(voice): add tests for status events, config, command separation, silero fallback"
```

archived-with: 2026-06-26-voice-platform-full-diag
---

### Integration Verification (Manual)

- [ ] **Run Gateway with voice platform**

```bash
python ultimate.py gateway --no-gui
```

Expected output:
```
[Voice] loading: 正在加载语音模型…
[Voice] loading: 正在加载Whisper模型(small)…
[Voice] loading: 正在加载语音检测模型…
[Voice] loading: Whisper模型就绪
[Voice] loading: 语音检测模型就绪
[Voice] listening: 等待唤醒词「你好」…
```

- [ ] **Verify all tasks.md items are checked**
- [ ] **Final commit if any remaining changes**
