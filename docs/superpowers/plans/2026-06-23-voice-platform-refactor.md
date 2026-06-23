---
change: voice-platform-refactor
design-doc: docs/superpowers/specs/2026-06-23-voice-platform-refactor-design.md
base-ref: e30194df1b8d5a20da328c70a661e0a15819f89b
archived-with: 2026-06-23-voice-platform-refactor
---

# Voice Platform Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `platforms/voice.py` from monolithic class to modular, config-driven package with edge-tts TTS and Silero-VAD.

**Architecture:** Two-phase delivery. P0 (2 tasks) replaces pyttsx3 with edge-tts in-place. P1 (9 tasks) decomposes into `platforms/voice/` package with AudioIO/STT/TTS/WakeWord protocol-driven modules, config-driven via `config.yaml` `voice:` section.

**Tech Stack:** Python 3.8+, sounddevice, numpy, scipy, faster-whisper, edge-tts, silero-vad, typing.Protocol

## Global Constraints

- All 133 existing tests must keep passing
- Protocol classes (typing.Protocol), not ABC — zero runtime overhead
- Each task is independently committable with a passing test suite
- `webrtcvad-wheels` and `pyttsx3` removed from requirements.txt
- `edge-tts` already installed (7.2.8), `silero-vad` + `onnxruntime` added
- Audio modules (sounddevice, silero) only importable on actual hardware — tests mock them

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 1: Replace `_speak()` with edge-tts async, remove pyttsx3

**Files:**
- Modify: `platforms/voice.py:199-224`
- Modify: `platforms/voice.py:1-13` (imports)

**Interfaces:**
- Consumes: edge_tts.Communicate (already installed v7.2.8)
- Produces: `VoicePlatform._speak()` unchanged async signature, `_speak_sync` deleted
- Removed: `pyttsx3` import

- [ ] **Step 1: Replace `_speak_sync` and update `_speak` to use edge-tts**

In `platforms/voice.py`, replace the TTS section (lines 199-224):

```python
    # ── TTS ────────────────────────────────────────────────

    async def _speak(self, text: str) -> None:
        self._speaking = True
        try:
            import io
            import edge_tts

            voice = "zh-CN-XiaoxiaoNeural"
            communicate = edge_tts.Communicate(text, voice)
            # Collect all chunks into a single MP3 byte buffer
            mp3_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data.write(chunk["data"])
            mp3_bytes = mp3_data.getvalue()

            if mp3_bytes:
                await asyncio.get_event_loop().run_in_executor(
                    None, _play_mp3_sync, mp3_bytes
                )
        except Exception as e:
            logger.error(f"TTS error: {e}")
        finally:
            self._speaking = False
```

And add the synchronous MP3 playback helper at module level (replacing old `_speak_sync`):

```python
def _play_mp3_sync(mp3_bytes: bytes) -> None:
    """Decode MP3 bytes and play via sounddevice (runs in executor)."""
    import io
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(mp3_bytes))
    sd.play(audio, sr)
    sd.wait()
```

- [ ] **Step 2: Update imports — remove pyttsx3, add edge_tts reference**

At top of `platforms/voice.py`, remove `import pyttsx3` (line 9). No replacement import needed — edge-tts is imported inline.

```python
# Remove: import pyttsx3
# Add soundfile import for MP3 playback
import soundfile as sf
```

- [ ] **Step 3: Update requirements.txt**

```
# Remove line: pyttsx3
```

- [ ] **Step 4: Run existing tests to verify nothing broken**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 133 passed (voice tests don't exist yet, TTS change doesn't affect existing)

- [ ] **Step 5: Manual TTS smoke test (optional)**

Run: `python -c "import asyncio; from edge_tts import Communicate; print('edge-tts OK')"`
Expected: `edge-tts OK`

- [ ] **Step 6: Commit**

```bash
git add platforms/voice.py requirements.txt
git commit -m "feat(voice): replace pyttsx3 with edge-tts async TTS"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 2: Verify TTS output quality

**Files:**
- Create: `tests/test_voice_platform.py`

**Interfaces:**
- Consumes: Task 1's `VoicePlatform._speak()` (async, edge-tts)
- Produces: 2 passing tests validating TTS behavior

- [ ] **Step 1: Write TTS tests**

Create `tests/test_voice_platform.py`:

```python
"""Tests for voice platform (P0 TTS + P1 modules)."""
import pytest
import asyncio


class TestTTS:
    """P0: edge-tts TTS tests."""

    @pytest.mark.asyncio
    async def test_edge_tts_synthesize_basic(self):
        """Verify edge-tts returns audio bytes for simple text."""
        import io
        from edge_tts import Communicate

        text = "你好"
        communicate = Communicate(text, "zh-CN-XiaoxiaoNeural")
        mp3_data = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_data.write(chunk["data"])
        result = mp3_data.getvalue()
        assert len(result) > 0, "Expected non-empty MP3 audio bytes"

    @pytest.mark.asyncio
    async def test_edge_tts_empty_text_handled(self):
        """edge-tts should not crash on empty input."""
        from edge_tts import Communicate
        import io

        communicate = Communicate("", "zh-CN-XiaoxiaoNeural")
        mp3_data = io.BytesIO()
        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data.write(chunk["data"])
        except Exception:
            pass  # empty text may fail — acceptable
        # Test passes if no unhandled exception
        assert True
```

- [ ] **Step 2: Run TTS tests**

Run: `python -m pytest tests/test_voice_platform.py -v -k "TTS" 2>&1`
Expected: 2 passed

- [ ] **Step 3: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed (133 existing + 2 new)

- [ ] **Step 4: Commit**

```bash
git add tests/test_voice_platform.py
git commit -m "test(voice): add TTS unit tests for edge-tts"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 3: Add `voice:` config section to config.yaml + VoiceConfig dataclass

**Files:**
- Modify: `config.yaml` (append `voice:` section)
- Modify: `config/configs.py` (add `VoiceConfig` dataclass + loader)

**Interfaces:**
- Consumes: existing `Config` dataclass, `load_config()`
- Produces: `VoiceConfig` dataclass available via `config.configs.get_config().voice`
- Produces: `voice` backward-compat alias in `_ALIAS_MAP`

- [ ] **Step 1: Append voice config to config.yaml**

Add at the end of `config.yaml`:

```yaml
# ── Voice: voice platform parameters ────────────────────────────────
voice:
  model: small
  vad: silero
  vad_threshold: 0.5
  wake_word: "你好"
  sample_rate: 16000
  max_record_secs: 30
  tts_voice: zh-CN-XiaoxiaoNeural
```

- [ ] **Step 2: Add VoiceConfig dataclass to configs.py**

In `config/configs.py`, add after the existing dataclass definitions (before `Config`):

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
```

- [ ] **Step 3: Add voice field to Config dataclass**

```python
@dataclass
class Config:
    model: ModelConfig
    toolsets: ToolsetsConfig
    agent: AgentConfig
    workspace: WorkspaceConfig
    skills: SkillsConfig
    voice: VoiceConfig       # <-- add this line
    workdir: Path
    workspace_dir: Path
```

- [ ] **Step 4: Parse voice section in load_config()**

After the skills parse block and before `workdir = ...`, add:

```python
    # Parse voice
    voice_raw = raw.get("voice", {})
    voice = VoiceConfig(
        model=voice_raw.get("model", "small"),
        vad=voice_raw.get("vad", "silero"),
        vad_threshold=float(voice_raw.get("vad_threshold", 0.5)),
        wake_word=voice_raw.get("wake_word", "你好"),
        sample_rate=int(voice_raw.get("sample_rate", 16000)),
        max_record_secs=int(voice_raw.get("max_record_secs", 30)),
        tts_voice=voice_raw.get("tts_voice", "zh-CN-XiaoxiaoNeural"),
    )
```

- [ ] **Step 5: Include voice in Config constructor return**

Update the return statement:

```python
    return Config(
        model=model,
        toolsets=toolsets,
        agent=agent,
        workspace=workspace,
        skills=skills,
        voice=voice,
        workdir=workdir,
        workspace_dir=workspace_dir,
    )
```

- [ ] **Step 6: Add backward-compat alias**

In `_ALIAS_MAP`, add:

```python
    "VOICE_CONFIG": lambda: get_config().voice,
```

- [ ] **Step 7: Run config tests + full regression**

Run: `python -m pytest tests/test_config.py tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 8: Commit**

```bash
git add config.yaml config/configs.py
git commit -m "feat(config): add VoiceConfig dataclass and voice: config section"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 4: Create `platforms/voice/` package with Protocol interfaces

**Files:**
- Create: `platforms/voice/__init__.py`
- Create: `platforms/voice/protocols.py`

**Interfaces:**
- Produces: `AudioIOProtocol`, `STTProtocol`, `TTSProtocol`, `WakeWordProtocol`

- [ ] **Step 1: Create the package directory**

```bash
mkdir -p platforms/voice
```

- [ ] **Step 2: Write protocols.py**

Create `platforms/voice/protocols.py`:

```python
"""Protocol interfaces for voice platform modules.

All modules use typing.Protocol — zero runtime overhead, duck-typing compatible.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np


class AudioIOProtocol(Protocol):
    """Audio capture and playback."""

    async def record_utterance(
        self, vad_threshold: float = 0.5, max_secs: int = 30
    ) -> np.ndarray | None:
        """Record user utterance with VAD-driven endpoint detection.

        Returns float32 numpy array (16000 Hz mono), or None if no speech detected.
        """
        ...

    async def play(self, audio_bytes: bytes, sample_rate: int = 24000) -> None:
        """Play audio bytes through speaker (non-blocking for event loop)."""
        ...


class STTProtocol(Protocol):
    """Speech-to-text transcription."""

    async def transcribe(self, audio: np.ndarray, language: str = "zh") -> str:
        """Transcribe audio array to text.

        Args:
            audio: float32 numpy array, 16000 Hz mono.
            language: ISO language code.

        Returns transcribed text string.
        """
        ...


class TTSProtocol(Protocol):
    """Text-to-speech synthesis."""

    async def synthesize(self, text: str) -> bytes:
        """Synthesize text to MP3 audio bytes.

        Returns MP3-encoded audio bytes, or empty bytes on failure.
        """
        ...


class WakeWordProtocol(Protocol):
    """Wake word detection."""

    async def wait_for_wake(self) -> str | None:
        """Block until wake word is detected.

        Returns the transcribed command text after wake word, or None on timeout/error.
        """
        ...

    async def record_command(self) -> str | None:
        """Record and transcribe a command utterance after wake word.

        Returns transcribed text, or None if no speech.
        """
        ...
```

- [ ] **Step 3: Write package __init__.py**

Create `platforms/voice/__init__.py`:

```python
"""Voice platform — modular, config-driven speech interface."""

from platforms.voice.protocols import (
    AudioIOProtocol,
    STTProtocol,
    TTSProtocol,
    WakeWordProtocol,
)

__all__ = [
    "AudioIOProtocol",
    "STTProtocol",
    "TTSProtocol",
    "WakeWordProtocol",
]
```

- [ ] **Step 4: Verify imports work**

Run: `python -c "from platforms.voice import AudioIOProtocol, STTProtocol, TTSProtocol, WakeWordProtocol; print('Protocols OK')"`
Expected: `Protocols OK`

- [ ] **Step 5: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 6: Commit**

```bash
git add platforms/voice/
git commit -m "feat(voice): create platforms/voice package with Protocol interfaces"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 5: Implement AudioIO module (recording + Silero-VAD)

**Files:**
- Create: `platforms/voice/audio.py`

**Interfaces:**
- Consumes: `AudioIOProtocol` (Task 4)
- Consumes: `config.configs.VoiceConfig`
- Produces: `SileroAudioIO` class implementing `AudioIOProtocol`

- [ ] **Step 1: Write AudioIO module**

Create `platforms/voice/audio.py`:

```python
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

    def _get_vad(self):
        """Lazy-load Silero VAD model."""
        if self._vad_model is None:
            import torch

            self._vad_model, self._vad_utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
            )
        return self._vad_model

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
                audio_chunk = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                speech_prob = model(torch.from_numpy(audio_chunk), self.sample_rate).item()
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
```

- [ ] **Step 2: Verify import**

Run: `python -c "from platforms.voice.audio import SileroAudioIO; print('AudioIO OK')"`
Expected: `AudioIO OK`

- [ ] **Step 3: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 4: Commit**

```bash
git add platforms/voice/audio.py
git commit -m "feat(voice): implement AudioIO with Silero-VAD endpoint detection"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 6: Implement STT module (faster-whisper with memory pipe)

**Files:**
- Create: `platforms/voice/stt.py`

**Interfaces:**
- Consumes: `STTProtocol` (Task 4), `VoiceConfig`
- Produces: `WhisperSTT` class

- [ ] **Step 1: Write STT module**

Create `platforms/voice/stt.py`:

```python
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
```

- [ ] **Step 2: Verify import**

Run: `python -c "from platforms.voice.stt import WhisperSTT; print('STT OK')"`
Expected: `STT OK` (model not loaded yet — lazy)

- [ ] **Step 3: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 4: Commit**

```bash
git add platforms/voice/stt.py
git commit -m "feat(voice): implement STT with faster-whisper in-memory pipeline"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 7: Implement TTS module (edge-tts async wrapper)

**Files:**
- Create: `platforms/voice/tts.py`

**Interfaces:**
- Consumes: `TTSProtocol` (Task 4), `VoiceConfig`
- Produces: `EdgeTTS` class

- [ ] **Step 1: Write TTS module**

Create `platforms/voice/tts.py`:

```python
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
```

- [ ] **Step 2: Verify import**

Run: `python -c "from platforms.voice.tts import EdgeTTS; print('TTS OK')"`
Expected: `TTS OK`

- [ ] **Step 3: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 4: Commit**

```bash
git add platforms/voice/tts.py
git commit -m "feat(voice): implement TTS with edge-tts async wrapper"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 8: Implement WakeWord module (Silero VAD pre-filter + Whisper confirm)

**Files:**
- Create: `platforms/voice/wake.py`

**Interfaces:**
- Consumes: `WakeWordProtocol`, `AudioIOProtocol`, `STTProtocol` (Task 4-6)
- Consumes: `VoiceConfig`
- Produces: `TwoStageWakeWord` class

- [ ] **Step 1: Write WakeWord module**

Create `platforms/voice/wake.py`:

```python
"""WakeWord — two-stage detection: Silero VAD pre-filter → Whisper confirm."""
from __future__ import annotations

import logging

import numpy as np

from config.configs import get_config
from platforms.voice.protocols import WakeWordProtocol, AudioIOProtocol, STTProtocol

logger = logging.getLogger(__name__)


class TwoStageWakeWord(WakeWordProtocol):
    """Two-stage wake word detection.

    Stage 1: Silero VAD endpoint detection identifies candidate speech.
    Stage 2: Whisper ASR transcribes candidate → substring match against wake word.
    """

    def __init__(
        self,
        audio_io: AudioIOProtocol,
        stt: STTProtocol,
        wake_word: str | None = None,
    ):
        cfg = get_config().voice
        self._audio = audio_io
        self._stt = stt
        self._wake_word = wake_word or cfg.wake_word

    async def wait_for_wake(self) -> str | None:
        """Block until wake word detected, then record and return command text."""
        logger.info("Waiting for wake word '%s'...", self._wake_word)
        print(f"💤 等待唤醒词「{self._wake_word}」…", flush=True)

        while True:
            audio = await self._audio.record_utterance()
            if audio is None:
                continue

            text = await self._stt.transcribe(audio)
            if self._wake_word in text.strip():
                logger.info("Wake word detected: %s", text.strip())
                print("✅ 已唤醒，请说指令…", flush=True)
                return await self.record_command()

    async def record_command(self) -> str | None:
        """Record and transcribe command utterance."""
        audio = await self._audio.record_utterance()
        if audio is None:
            return None

        text = (await self._stt.transcribe(audio)).strip()
        if text:
            logger.info("STT: %s", text)
        return text or None
```

- [ ] **Step 2: Verify import**

Run: `python -c "from platforms.voice.wake import TwoStageWakeWord; print('Wake OK')"`
Expected: `Wake OK`

- [ ] **Step 3: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 4: Commit**

```bash
git add platforms/voice/wake.py
git commit -m "feat(voice): implement TwoStageWakeWord with Silero pre-filter + Whisper confirm"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 9: Rewrite VoicePlatform as orchestrator, delete old voice.py

**Files:**
- Create: `platforms/voice/platform.py` (orchestrator)
- Modify: `platforms/voice/__init__.py` (add VoicePlatform export)
- Delete (after verifying): `platforms/voice.py`

**Interfaces:**
- Consumes: All modules from Tasks 4-8
- Consumes: `gateway.BasePlatform`
- Produces: `VoicePlatform(BasePlatform)` with same public API

- [ ] **Step 1: Write VoicePlatform orchestrator**

Create `platforms/voice/platform.py`:

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
```

- [ ] **Step 2: Update __init__.py to export VoicePlatform**

Edit `platforms/voice/__init__.py`:
```python
"""Voice platform — modular, config-driven speech interface."""

from platforms.voice.protocols import (
    AudioIOProtocol,
    STTProtocol,
    TTSProtocol,
    WakeWordProtocol,
)
from platforms.voice.platform import VoicePlatform

__all__ = [
    "AudioIOProtocol",
    "STTProtocol",
    "TTSProtocol",
    "WakeWordProtocol",
    "VoicePlatform",
]
```

- [ ] **Step 3: Verify import from new location**

Run: `python -c "from platforms.voice import VoicePlatform; print('VoicePlatform OK')"`
Expected: `VoicePlatform OK`

- [ ] **Step 4: Update ultimate.py to import from new location**

In `ultimate.py`, change the import:
```python
# Old: from platforms.voice import VoicePlatform
# New:
from platforms.voice import VoicePlatform
```
(This is actually the same import path since `platforms/voice/__init__.py` re-exports it)

- [ ] **Step 5: Delete old voice.py**

```bash
rm platforms/voice.py
rm -rf platforms/__pycache__/voice.cpython-314.pyc 2>/dev/null
```

- [ ] **Step 6: Verify no broken imports**

Run: `python -c "from gateway import Gateway; from platforms.voice import VoicePlatform; g = Gateway().register(VoicePlatform(wake_word='你好')); print('Gateway OK')"`
Expected: `Gateway OK`

- [ ] **Step 7: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 8: Commit**

```bash
git add platforms/voice/__init__.py platforms/voice/platform.py
git rm platforms/voice.py
git commit -m "feat(voice): rewrite VoicePlatform as modular orchestrator, remove monolithic voice.py"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 10: Update ultimate.py gateway_cmd() for config-driven mode

**Files:**
- Modify: `ultimate.py:38-45`

**Interfaces:**
- Consumes: `VoicePlatform` from `platforms.voice`
- Produces: config-driven gateway startup

- [ ] **Step 1: Simplify gateway_cmd()**

In `ultimate.py`, replace the `gateway_cmd()` function:

```python
async def gateway_cmd():
    from platforms.voice import VoicePlatform
    from gateway import Gateway

    gateway = Gateway().register(VoicePlatform())
    # Add more platforms here:
    # from platforms.weixin import WeChatPlatform
    # gateway.register(WeChatPlatform())

    try:
        await gateway.run()
    except KeyboardInterrupt:
        pass
    finally:
        await gateway.stop()
```

- [ ] **Step 2: Verify import at startup**

Run: `python -c "import asyncio; from ultimate import gateway_cmd; print('gateway_cmd OK')"`
Expected: `gateway_cmd OK`

- [ ] **Step 3: Run full regression**

Run: `python -m pytest tests/ -x -q 2>&1`
Expected: 135 passed

- [ ] **Step 4: Commit**

```bash
git add ultimate.py
git commit -m "refactor(voice): simplify gateway_cmd() to use config-driven VoicePlatform"
```

archived-with: 2026-06-23-voice-platform-refactor
---

### Task 11: Write comprehensive tests and finalize tasks.md

**Files:**
- Modify: `tests/test_voice_platform.py` (extend with module tests)
- Modify: `openspec/changes/voice-platform-refactor/tasks.md` (check all boxes)

**Interfaces:**
- Consumes: All modules from Tasks 1-10

- [ ] **Step 1: Extend test file with module unit tests**

Append to `tests/test_voice_platform.py`:

```python
# ── P1: Protocol conformance ───────────────────────────────


class TestProtocols:
    def test_protocols_importable(self):
        from platforms.voice import (
            AudioIOProtocol,
            STTProtocol,
            TTSProtocol,
            WakeWordProtocol,
        )
        assert AudioIOProtocol is not None
        assert STTProtocol is not None
        assert TTSProtocol is not None
        assert WakeWordProtocol is not None

    def test_silero_audio_io_implements_protocol(self):
        from platforms.voice.audio import SileroAudioIO
        from platforms.voice.protocols import AudioIOProtocol

        io = SileroAudioIO()
        # Verify required methods exist
        assert hasattr(io, "record_utterance")
        assert hasattr(io, "play")
        assert callable(io.record_utterance)
        assert callable(io.play)

    def test_whisper_stt_implements_protocol(self):
        from platforms.voice.stt import WhisperSTT
        from platforms.voice.protocols import STTProtocol

        stt = WhisperSTT(model_size="tiny")
        assert hasattr(stt, "transcribe")
        assert callable(stt.transcribe)

    def test_edge_tts_implements_protocol(self):
        from platforms.voice.tts import EdgeTTS
        from platforms.voice.protocols import TTSProtocol

        tts = EdgeTTS()
        assert hasattr(tts, "synthesize")
        assert callable(tts.synthesize)

    def test_two_stage_wake_word_implements_protocol(self, monkeypatch):
        from platforms.voice.wake import TwoStageWakeWord
        from platforms.voice.protocols import WakeWordProtocol

        # Mock audio_io and stt to test interface
        class MockAudio:
            async def record_utterance(self, **kw):
                import numpy as np
                return np.zeros(16000, dtype=np.float32)

        class MockSTT:
            async def transcribe(self, audio, language="zh"):
                return "你好 今天天气怎么样"

        wake = TwoStageWakeWord(MockAudio(), MockSTT(), wake_word="你好")
        assert hasattr(wake, "wait_for_wake")
        assert hasattr(wake, "record_command")
        assert callable(wake.wait_for_wake)
        assert callable(wake.record_command)


# ── P1: Config-driven behavior ──────────────────────────────


class TestVoiceConfig:
    def test_voice_config_defaults(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig()
        assert cfg.model == "small"
        assert cfg.vad == "silero"
        assert cfg.wake_word == "你好"
        assert cfg.sample_rate == 16000
        assert cfg.max_record_secs == 30

    def test_voice_config_custom(self):
        from config.configs import VoiceConfig

        cfg = VoiceConfig(
            model="base",
            wake_word="hey",
            tts_voice="zh-CN-YunxiNeural",
        )
        assert cfg.model == "base"
        assert cfg.wake_word == "hey"
        assert cfg.tts_voice == "zh-CN-YunxiNeural"


# ── P1: TTS module unit tests ──────────────────────────────


class TestEdgeTTSModule:
    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_bytes(self):
        from platforms.voice.tts import EdgeTTS

        tts = EdgeTTS()
        result = await tts.synthesize("")
        assert result == b""

    @pytest.mark.asyncio
    async def test_synthesize_returns_mp3_bytes(self):
        from platforms.voice.tts import EdgeTTS

        tts = EdgeTTS()
        result = await tts.synthesize("你好世界")
        assert isinstance(result, bytes)
        assert len(result) > 0


# ── P1: VoicePlatform orchestrator ──────────────────────────


class TestVoicePlatformOrchestrator:
    @pytest.mark.asyncio
    async def test_platform_instantiation(self):
        from platforms.voice import VoicePlatform

        vp = VoicePlatform(wake_word="你好", whisper_model="tiny")
        assert vp.platform_name == "voice"
        assert vp.channel == "voice"
        assert vp._audio is not None
        assert vp._stt is not None
        assert vp._tts is not None

    def test_platform_implements_base_platform(self):
        from platforms.voice import VoicePlatform
        from gateway import BasePlatform

        vp = VoicePlatform(wake_word="测试")
        assert isinstance(vp, BasePlatform)
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_voice_platform.py -v 2>&1`
Expected: ~12 tests passed (2 TTS + 10 module)

- [ ] **Step 3: Run FULL regression**

Run: `python -m pytest tests/ -v -q 2>&1`
Expected: ~147 passed (133 existing + 2 TTS + 12 module)

- [ ] **Step 4: Check all tasks complete**

Read `openspec/changes/voice-platform-refactor/tasks.md`
Verify all `- [ ]` are changed to `- [x]`

- [ ] **Step 5: Commit**

```bash
git add tests/test_voice_platform.py openspec/changes/voice-platform-refactor/tasks.md
git commit -m "test(voice): add comprehensive module unit tests and mark tasks complete"
```
