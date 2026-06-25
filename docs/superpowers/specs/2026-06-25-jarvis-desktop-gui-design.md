---
comet_change: jarvis-desktop-gui
role: technical-design
canonical_spec: openspec
depends_on: provider-streaming-refactor
archived-with: 2026-06-25-jarvis-desktop-gui
status: final
---

# JARVIS Desktop GUI — Technical Design

## Architecture Overview

```
ultimate.py gateway
  │
  ├── subprocess.Popen → Tauri App (ui/)
  │                       Rust: window mgr + WS client
  │                       Vue3: JARVIS UI
  │
  ├── VoicePlatform (wake→STT→LLM→TTS)
  │     └── broadcast → TauriPlatform → WS → Tauri
  │
  ├── TauriPlatform (aiohttp WS Server :18765)
  │
  └── AgentRunner (on_text_chunk → TauriPlatform broadcast)
```

**New/Modified Files**: See plan for exact file listing.

## Key Decisions

### D1: Tauri v1 + Vue3 + TypeScript
Tauri v1 for mature Windows support. Vue3 for reactive UI. No UI component library — pure custom JARVIS theme.

### D2: Rust WS Client + Vue3 via Tauri Events
Rust layer holds `tokio-tungstenite` WS connection. Messages converted to Tauri events (`tauri://wake`, `tauri://text-chunk`, etc.). Vue3 listens via `@tauri-apps/api/event`. Retry with exponential backoff (500ms→10s, max 10 retries).

### D3: Backend Listening, Tauri is Passive
VoicePlatform (Python) owns the microphone. On wake, broadcasts `wake` event to GUI. Tauri App starts hidden in system tray, only shows on `wake`.

### D4: Process Management
`ultimate.py gateway` spawns Tauri via `subprocess.Popen`. `--no-gui` flag disables. Python shutdown kills Tauri subprocess. Tauri binary auto-discovery: project root → PATH → config.yaml path.

### D5: Hybrid Waveform (Scheme C)
- Idle/thinking/TTS → preset animations (breath/pulse/active)
- STT/listening → backend pushes `{"event": "amplitude", "rms": 0.42}` at 10fps
- Frontend linearly interpolates between data points for smooth 60fps rendering
- Canvas 2D ring waveform via requestAnimationFrame

### D6: Frameless Window
`tauri.conf.json`: `"decorations": false`. Draggable via `data-tauri-drag-region` on header area. Self-drawn close button hides (doesn't quit).

### D7: Progressive Reveal Layout (Scheme C)
5 visual states driven by events:
```
hidden → waveform-only → waveform+thinking → waveform+conversation → waveform+conv+table
```
- Waveform always visible once shown
- Conversation area slides in on first `text_chunk`
- Table appears as overlay/modal on `data` event
- Input bar only visible when conversation area is shown

### D8: Input — Inline in Conversation Area
Text input embedded at bottom of conversation view. Appears when conversation area expands. Enter sends text via Tauri invoke → Rust WS → Python.

### D9: Conversation History Preserved
New `wake` does NOT clear history. Visual separator between rounds. New messages appended below previous.

### D10: Streaming via on_text_chunk
AgentRunner's `on_text_chunk` callback (implemented in `provider-streaming-refactor`) feeds text to TauriPlatform broadcast. VoicePlatform passes the callback through.

### D11: Stream Interruption Recovery
If stream breaks: AgentRunner returns `""`, VoicePlatform broadcasts `error` event. GUI marks last assistant bubble as "interrupted" with error icon. On next successful reply, old interrupted bubble is replaced.

## WS Protocol

### Backend → Frontend
| Event | Payload | Trigger |
|-------|---------|---------|
| `wake` | `{}` | Wake word detected |
| `stt` | `{"text": "..."}` | Speech recognized |
| `thinking` | `{}` | LLM call started |
| `text_chunk` | `{"text": "..."}` | LLM streaming chunk |
| `data` | `{"type":"table","columns":[...],"rows":[...]}` | Structured data |
| `amplitude` | `{"rms": 0.42}` | 10fps during listening |
| `tts_start` | `{}` | TTS playback started |
| `tts_end` | `{}` | TTS playback ended |
| `idle` | `{}` | Interaction complete |
| `error` | `{"reason":"stream_interrupted"}` | Stream broke |

### Frontend → Backend
| Event | Payload | |
|-------|---------|---|
| `input` | `{"text": "..."}` | Keyboard input |
| `close` | `{}` | User clicked close |

## UI State Machine

```
hidden ──wake──► waveform ──stt──► thinking ──text_chunk──► conversing
   ▲                                                              │
   │                          data ┌──────────────────────────────┘
   │                               ▼
   │                          showingData
   │                               │
   └────── idle + 10s timeout ─────┘
```

- New event during idle countdown → cancel countdown
- New wake → start new round (history preserved)
- Close button → fade-out + hide (app stays in tray)

## Vue3 Component Tree

```
App.vue
├── JarvisWaveform.vue    (Canvas ring, 60fps rAF, mode prop)
├── ConversationView.vue  (slide-in, scrollable, auto-scroll)
│   ├── MessageBubble.vue (user/agent, streaming typewriter)
│   └── InputBar.vue      (text input, enter to send)
└── DataTable.vue         (overlay, JARVIS themed)
```

## Testing Strategy

- Python: Unit tests for TauriPlatform WS server + broadcast
- Python: Integration test for VoicePlatform → broadcast hook points
- Rust: Manual verification (window behavior, WS reconnect)
- Vue3: Manual verification (state machine, animations, rendering)
- E2E: Full flow manual test (gateway → wake → waveform → conversation → table → hide)
