---
comet_change: voice-platform-full-diag
role: technical-design
canonical_spec: openspec
---

# Voice Platform Full-Chain Fix — Technical Design

## Summary

Fix 7 bottlenecks identified via full-chain diagnostic of `platforms/voice/`. Addresses blocking hangs (P0), redundant STT (P1), and UX gaps (P2-P3) through 6 targeted changes across 6 files.

## Decisions

### D1: Status Feedback — Callback Injection

Each component accepts optional `status_callback: Callable[[str, str], Awaitable[None]]`. VoicePlatform injects `_broadcast_status()` which pushes events to Tauri GUI (WebSocket broadcast) and prints to terminal.

**Rationale**: Consistent with existing DI pattern (Protocol-based components). No new infrastructure (no event bus). Trivially testable — inject mock callback, assert events and order.

**Stages**: `loading` → `listening` → `transcribing` → `thinking` → `speaking` → `idle`

### D2: Smart Command Separation — Wake Word Extraction + 8s Fallback

In `TwoStageWakeWord.wait_for_wake()`, after a single STT transcription, find wake word position and extract text after it as the command. If the post-wake text is empty or < 2 meaningful chars, fall back to `record_command()` with 8s timeout (was 30s).

**Rationale**: Eliminates the second STT call in the common case where user says "你好，<command>" in one breath. The 8s fallback timeout reflects that an already-awakened user will speak promptly.

**Boundary handling**:
| Scenario | Behavior |
|----------|----------|
| "你好，今天天气" | Command = "今天天气" → send |
| "你好" (only wake) | Fallback → record_command(8s) |
| "你好你好你好" (noise) | < 2 meaningful chars → fallback |
| VAD false trigger → empty STT | Continue waiting |

### D3: Model Warmup — Startup-Phase Parallel Preload

`VoicePlatform.start()` preloads Whisper and Silero VAD in parallel, each with configurable timeout. Success → broadcasts "模型就绪"; failure → logs warning, falls back to amplitude VAD, continues. `WhisperSTT._get_model()` becomes no-op if already loaded. `SileroAudioIO._record_sync()` skips `torch.hub.load` if preloaded, uses amplitude fallback if not.

**Rationale**: Moves all blocking I/O to startup where user expects latency and sees progress ("正在加载语音模型…"). Eliminates mid-interaction hangs. Thread-level cancellation not needed — async timeout at task level is sufficient.

```python
async def start(self):
    await self._broadcast_status("loading", "正在加载语音模型…")
    whisper_ok = await self._warmup_whisper(timeout=60)
    silero_ok = await self._warmup_silero(timeout=15)
    if not silero_ok:
        self._audio._vad_available = False
    await self._broadcast_status("listening", f"等待唤醒词「{self._wake_word}」…")
    asyncio.create_task(self._listen_loop())
```

### D4: STT Parameter Tuning

- `vad_filter`: `True` → `False` (Silero VAD already filtered in recording stage; removes redundant ~20% overhead)
- `beam_size`: `5` → `3` (CPU int8 small model doesn't benefit from wide beam; ~15% speedup)

### D5: Busy-Wait → Event-Driven

Replace `while self._speaking: await asyncio.sleep(0.05)` with `asyncio.Event`. `_speak()` sets `self._speak_done` on completion; `_listen_loop()` awaits it.

### D6: New VoiceConfig Fields

```python
stt_beam_size: int = 3
stt_vad_filter: bool = False
silero_download_timeout: int = 15
stt_model_warmup: bool = True
status_verbose: bool = True
```

## Data Flow (After)

```
Mic → VAD → STT (transcribe once)
                  │
                  ├─ "你好，<cmd>" → extract cmd → Agent (no second STT!)  ← D2
                  │
                  └─ "你好" only → record_command(8s) → STT → Agent
                                                              │
                                                              ▼
                                                         LLM → TTS → Speaker
                    │                                      │
                    └──── status events at every stage ────┘             ← D1
```

## Error Handling

| Layer | Strategy |
|-------|----------|
| Silero warmup timeout | Log warning, set `_vad_available=False`, use amplitude VAD |
| Whisper warmup timeout | Raise at startup (fail-fast — STT is critical) |
| STT transient error | Log, continue listening loop |
| TTS network error | `TTSException` → logged, no crash |
| Status broadcast error | Catch, log debug, never crash the platform |

## Files Changed

| File | Change |
|------|--------|
| `platforms/voice/platform.py` | Status broadcast, event-driven busy-wait, warmup orchestration |
| `platforms/voice/audio.py` | Silero preload/warmup, fallback flag, status callback |
| `platforms/voice/stt.py` | beam_size/vad_filter config-driven, warmup support, status callback |
| `platforms/voice/wake.py` | Smart command separation, 8s fallback timeout, status callback |
| `gateway/events.py` | New `status_event()` factory |
| `config/configs.py` | VoiceConfig: 5 new fields |
| `config.yaml` | voice section: 5 new keys |
| `tests/test_voice_platform.py` | New tests for warmup, separation, fallback, status events |

## Testing Strategy

**Unit tests (pytest, no hardware)**:
- Mock `status_callback`, verify correct stage sequence per interaction path
- Parametrize `wait_for_wake()` with 5 boundary text inputs, assert correct command extraction
- Mock `torch.hub.load` raising → assert amplitude VAD fallback
- Mock `WhisperModel` load timeout → assert startup raises

**Integration (requires real hardware, manual)**:
- Cold start: verify "正在加载语音模型…" shows, then "等待唤醒词…"
- Hot start: full interaction latency < 20s
- Network disconnected: `torch.hub.load` failure → graceful degradation, no hang
- Wake word + inline command: verify single STT call (check logs)
