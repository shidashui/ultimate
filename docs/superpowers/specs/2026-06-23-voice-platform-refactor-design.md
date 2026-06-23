---
comet_change: voice-platform-refactor
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-23-voice-platform-refactor
status: final
---

# Voice Platform Refactor — Technical Design

## Summary

Refactor `platforms/voice.py` from a single-file monolithic class into a modular,
config-driven voice platform with independent, testable components. Upgrade TTS
from pyttsx3 to edge-tts and VAD from webrtcvad to Silero-VAD.

## Architecture

```
                     VoicePlatform (orchestrator)
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                 ▼
    ┌──────────┐    ┌───────────┐    ┌───────────┐
    │ AudioIO  │    │    STT    │    │    TTS    │
    │ sounddev │    │ faster-   │    │ edge-tts  │
    │ + Silero │    │ whisper   │    │ (async)   │
    └────┬─────┘    └─────┬─────┘    └─────┬─────┘
         │                │                │
    ┌────┴────┐           │                │
    ▼         ▼           │                │
┌───────┐ ┌───────┐       │                │
│Silero │ │WakeWord│      │                │
│ VAD   │ │Whisper│      │                │
│detect │ │confirm│      │                │
└───────┘ └───────┘      │                │
```

## Components

### AudioIO — `platforms/voice/audio.py`

**Protocol:**

```python
class AudioIOProtocol(Protocol):
    async def record_utterance(self, vad_threshold: float = 0.5, max_secs: int = 30) -> np.ndarray | None: ...
    async def play(self, audio_bytes: bytes, sample_rate: int = 24000) -> None: ...
```

**Implementation:**
- Recording: `sounddevice.RawInputStream` (SAMPLE_RATE=16000, mono, int16)
- VAD: `silero-vad` ONNX model, per-frame speech probability
- Endpoint detection: sliding window threshold, same triggered/ring logic as current code but with confidence scores
- Playback: `sounddevice.play()` + `sd.wait()` in executor (non-blocking)

### STT — `platforms/voice/stt.py`

**Protocol:**

```python
class STTProtocol(Protocol):
    async def transcribe(self, audio: np.ndarray, language: str = "zh") -> str: ...
```

**Implementation:**
- `faster-whisper` model, loaded once at init
- Audio passed via in-memory buffer (bytes conversion + `scipy.io.wavfile.write` to `io.BytesIO`), no temp file I/O
- Model size from config: `voice.model` (default `small`)

### TTS — `platforms/voice/tts.py`

**Protocol:**

```python
class TTSProtocol(Protocol):
    async def synthesize(self, text: str) -> bytes: ...
```

**Implementation:**
- `edge_tts.Communicate(text, voice)` → `await communicate.save()` or collect streamed chunks to bytes
- Full synthesis before playback (not streaming chunk-by-chunk)
- Voice from config: `voice.tts_voice` (default `zh-CN-XiaoxiaoNeural`)
- Network errors → `TTSException` with descriptive message

### WakeWord — `platforms/voice/wake.py`

**Protocol:**

```python
class WakeWordProtocol(Protocol):
    async def wait_for_wake(self) -> str | None: ...
    async def record_command(self) -> str | None: ...
```

**Implementation:**
- Two-stage pipeline:
  1. Silero VAD endpoint detection identifies candidate speech segments
  2. `faster-whisper` transcribes the candidate → substring match against `voice.wake_word`
- On match: records the command utterance (same VAD-driven recording)
- On no-match: continues waiting

### VoiceConfig — `config/configs.py`

```python
@dataclass
class VoiceConfig:
    model: str = "small"           # whisper model size
    vad: str = "silero"            # VAD backend
    vad_threshold: float = 0.5     # speech probability threshold
    wake_word: str = "你好"         # wake word phrase
    sample_rate: int = 16000       # audio sample rate Hz
    max_record_secs: int = 30      # max recording duration
    tts_voice: str = "zh-CN-XiaoxiaoNeural"  # edge-tts voice
```

## Dependency Changes

| Remove | Add |
|--------|-----|
| `pyttsx3` | (edge-tts already installed) |
| `webrtcvad-wheels` | `silero-vad`, `onnxruntime` (dependency of silero-vad) |

## Data Flow (P1 final form)

```
Mic → AudioIO.record_utterance() → PCM float32 array
                                       │
                              WakeWord.wait_for_wake()
                                       │
                          Silero VAD frames ──→ confidence > threshold?
                                       │ YES
                                       ▼
                          Faster-Whisper transcribe → "你好" in text?
                                       │ YES (match)
                                       ▼
                          AudioIO.record_utterance() → PCM array
                                       │
                                       ▼
                          STT.transcribe(audio) → text string
                                       │
                                       ▼
                          AgentRunner处理 → Reply text
                                       │
                                       ▼
                          TTS.synthesize(reply) → audio bytes (MP3)
                                       │
                                       ▼
                          AudioIO.play(audio_bytes) → speaker output
```

## Error Handling

| Layer | Strategy |
|-------|----------|
| AudioIO | `sd.PortAudioError` → log + return None (caller handles silence) |
| STT | `WhisperModel` load failure → raise at startup (fail-fast) |
| TTS | Network failure → `TTSException`, logged, propagated to VoicePlatform.send() |
| WakeWord | Transient ASR error → log + continue waiting, no crash |
| Orchestrator | Any unhandled exception → logged, 1s sleep, loop continues |

## Testing Strategy

- **AudioIO tests:** mock `sounddevice.RawInputStream` with pre-recorded PCM samples
- **STT tests:** inject pre-recorded audio, assert transcription text (CI may skip if model too large)
- **TTS tests:** mock HTTP layer, verify correct `edge_tts.Communicate` args
- **WakeWord tests:** inject known audio samples (wake word present / absent), verify detection
- **Integration test:** short canned audio → STT → TTS round-trip (may require real whisper model)
- **Regression:** all existing 133 tests must still pass

## Phased Implementation

**P0 (immediate):** Replace `_speak()` in `voice.py` with edge-tts, remove pyttsx3. Test manually.
**P1 (full refactor):** Create `platforms/voice/` package, migrate module by module. Delete old `voice.py`.
