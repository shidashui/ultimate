---
change: jarvis-desktop-gui
design-doc: docs/superpowers/specs/2026-06-25-jarvis-desktop-gui-design.md
base-ref: e0a080279f7356cab9c78b2dad19c8941a40a272
archived-with: 2026-06-25-jarvis-desktop-gui
---

# JARVIS Desktop GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Tauri v1 + Vue3 desktop GUI for Ultimate Agent with JARVIS-style holographic UI, progressive reveal layout, and WebSocket-based real-time communication.

**Architecture:** Three-layer stack — Python backend (TauriPlatform WS server + Gateway integration), Tauri Rust shell (window mgr + WS client + system tray), Vue3 frontend (JARVIS theme + Canvas waveform + streaming conversation + data table).

**Tech Stack:** Python 3.8+ (aiohttp), Tauri v1 (Rust + tokio-tungstenite), Vue3 + TypeScript + Vite, Canvas 2D API, CSS custom theme

## Global Constraints

- Python 3.8+ (no `match`/`case`)
- Tauri v1 (not v2)
- Frameless window with `data-tauri-drag-region`
- WS `ws://127.0.0.1:18765` (configurable)
- Progressive reveal layout (hidden → waveform → thinking → conversing → showingData)
- History preserved across wake rounds
- `--no-gui` flag on gateway command
- Tauri binary auto-discovery: project root → PATH → config.yaml

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 1: Python — Event Types Definition

**Files:**
- Create: `gateway/events.py`

**Interfaces:**
- Produces: Event type literals and typed dict helpers for WS protocol

- [ ] **Step 1: Create events.py**

```python
# gateway/events.py
"""Tauri ↔ Python WebSocket 事件类型定义。"""

# ── 后端 → 前端 ──
EVENT_WAKE = "wake"
EVENT_STT = "stt"
EVENT_THINKING = "thinking"
EVENT_TEXT_CHUNK = "text_chunk"
EVENT_DATA = "data"
EVENT_AMPLITUDE = "amplitude"
EVENT_TTS_START = "tts_start"
EVENT_TTS_END = "tts_end"
EVENT_IDLE = "idle"
EVENT_ERROR = "error"

# ── 前端 → 后端 ──
EVENT_INPUT = "input"
EVENT_CLOSE = "close"
EVENT_HELLO = "hello"


def wake_event() -> dict:
    return {"event": EVENT_WAKE}


def stt_event(text: str) -> dict:
    return {"event": EVENT_STT, "text": text}


def thinking_event() -> dict:
    return {"event": EVENT_THINKING}


def text_chunk_event(text: str) -> dict:
    return {"event": EVENT_TEXT_CHUNK, "text": text}


def data_table_event(columns: list[str], rows: list[list]) -> dict:
    return {"event": EVENT_DATA, "type": "table", "columns": columns, "rows": rows}


def amplitude_event(rms: float) -> dict:
    return {"event": EVENT_AMPLITUDE, "rms": rms}


def tts_start_event() -> dict:
    return {"event": EVENT_TTS_START}


def tts_end_event() -> dict:
    return {"event": EVENT_TTS_END}


def idle_event() -> dict:
    return {"event": EVENT_IDLE}


def error_event(reason: str) -> dict:
    return {"event": EVENT_ERROR, "reason": reason}
```

- [ ] **Step 2: Verify imports**

Run: `python -c "from gateway.events import wake_event, text_chunk_event; print(wake_event()); print(text_chunk_event('hello'))"`
Expected: `{'event': 'wake'}` and `{'event': 'text_chunk', 'text': 'hello'}`

- [ ] **Step 3: Commit**

```bash
git add gateway/events.py
git commit -m "feat: define WS event types and builder functions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 2: Python — TauriPlatform (WebSocket Server)

**Files:**
- Create: `gateway/tauri_platform.py`

**Interfaces:**
- Consumes: `gateway.events.EVENT_HELLO`
- Produces: `TauriPlatform(BasePlatform)` with `broadcast(event: dict)` and `send(reply: Reply)`

- [ ] **Step 1: Read existing gateway.py for BasePlatform interface**

Read `gateway/gateway.py` to verify `BasePlatform` abstract methods: `receive()`, `send()`, `platform_name`, `channel`.

- [ ] **Step 2: Create tauri_platform.py**

```python
# gateway/tauri_platform.py
import asyncio
import logging
from aiohttp import web

from gateway.gateway import BasePlatform, Message, Reply
from gateway.events import EVENT_HELLO

logger = logging.getLogger(__name__)

DEFAULT_WS_PORT = 18765


class TauriPlatform(BasePlatform):
    """Tauri 桌面应用平台 — WebSocket Server + 事件广播通道。"""

    platform_name = "tauri"
    channel = "desktop"

    def __init__(self, port: int = DEFAULT_WS_PORT):
        self.port = port
        self.connections: set[web.WebSocketResponse] = set()
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None

    # ── WebSocket handler ──

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections.add(ws)
        logger.info("[TauriPlatform] Client connected (%d total)", len(self.connections))

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = msg.json()
                    event = data.get("event", "")
                    if event == "hello":
                        logger.info("[TauriPlatform] Handshake: version=%s", data.get("version", "?"))
                    elif event == "input":
                        # 键盘输入 → 将由 Gateway._dispatch 处理
                        pass
                    elif event == "close":
                        logger.info("[TauriPlatform] Client requested close")
        except Exception:
            logger.debug("[TauriPlatform] Client connection error", exc_info=True)
        finally:
            self.connections.discard(ws)
            logger.info("[TauriPlatform] Client disconnected (%d remaining)", len(self.connections))

        return ws

    # ── BasePlatform interface ──

    async def receive(self) -> Message:
        """Tauri 端没有主动推送消息给 Gateway 的语义，但接口要求实现。"""
        while True:
            await asyncio.sleep(3600)

    async def send(self, reply: Reply) -> None:
        """向所有 Tauri 客户端广播回复文本。"""
        await self.broadcast({"event": "text_chunk", "text": reply.content})

    # ── Broadcast API ──

    async def broadcast(self, event: dict) -> None:
        """向所有连接的 Tauri 客户端推送事件。自动清理死连接。"""
        dead: set[web.WebSocketResponse] = set()
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except ConnectionError:
                dead.add(ws)
        self.connections -= dead

    # ── Lifecycle ──

    async def start(self) -> None:
        self._app = web.Application()
        self._app.router.add_get("/ws", self._ws_handler)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()
        logger.info("[TauriPlatform] WS server listening on ws://127.0.0.1:%d/ws", self.port)

    async def stop(self) -> None:
        for ws in list(self.connections):
            await ws.close()
        self.connections.clear()
        if self._runner:
            await self._runner.cleanup()
        logger.info("[TauriPlatform] WS server stopped")
```

- [ ] **Step 3: Verify imports**

Run: `python -c "from gateway.tauri_platform import TauriPlatform; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add gateway/tauri_platform.py
git commit -m "feat: add TauriPlatform WS server with broadcast API

- aiohttp WebSocket server on ws://127.0.0.1:18765/ws
- connection set management with auto-cleanup
- broadcast() for pushing events to all connected clients
- Full BasePlatform lifecycle (start/stop/send)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 3: Python — Gateway Integration + config.yaml

**Files:**
- Modify: `gateway/gateway.py`
- Modify: `ultimate.py`
- Modify: `config.yaml`

**Interfaces:**
- Consumes: `TauriPlatform` from Task 2
- Produces: `--no-gui` flag, `gui:` config section, Tauri subprocess management

- [ ] **Step 1: Add gui config to config.yaml**

Append to `config.yaml`:

```yaml
# ── GUI: Tauri desktop app ────────────────────────────────────
gui:
  ws_port: 18765
  tauri_bin: null                    # auto-detect if null
  auto_hide_delay: 10                # seconds before auto-hide
```

- [ ] **Step 2: Update ultimate.py gateway_cmd()**

In `ultimate.py`, add `--no-gui` argument and Tauri process management:

```python
async def gateway_cmd(args=None):
    from platforms.weixin import WeChatPlatform
    from platforms.voice import VoicePlatform
    from gateway import Gateway
    from gateway.tauri_platform import TauriPlatform
    import subprocess
    import os

    # ── Tauri 子进程 ──
    tauri_process = None
    no_gui = args and getattr(args, 'no_gui', False)

    if not no_gui:
        tauri_bin = _find_tauri_binary()
        if tauri_bin:
            try:
                tauri_process = subprocess.Popen([tauri_bin])
                print(f"[Gateway] Tauri App started (PID: {tauri_process.pid})")
            except Exception as e:
                print(f"[Gateway] Warning: Failed to start Tauri: {e}")
        else:
            print("[Gateway] Warning: Tauri binary not found, running without GUI")

    # ── 注册平台 ──
    gateway = (
        Gateway()
        .register(TauriPlatform(port=18765))
        .register(VoicePlatform(wake_word="你好"))
    )

    try:
        await gateway.run()
    except KeyboardInterrupt:
        pass
    finally:
        await gateway.stop()
        if tauri_process:
            tauri_process.terminate()
            try:
                tauri_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tauri_process.kill()
            print("[Gateway] Tauri App stopped")


def _find_tauri_binary() -> str | None:
    """查找 Tauri 二进制文件。"""
    import os
    import shutil
    candidates = [
        os.path.join(os.path.dirname(__file__), "ui", "src-tauri", "target", "release", "jarvis-ui.exe"),
        os.path.join(os.path.dirname(__file__), "ui", "src-tauri", "target", "debug", "jarvis-ui.exe"),
        shutil.which("jarvis-ui"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None
```

Also add `--no-gui` argument to the argument parser:

```python
parser.add_argument("--no-gui", action="store_true", help="Disable Tauri GUI")
```

Change `gateway_cmd()` signature to receive args:

```python
elif args.command == "gateway":
    asyncio.run(gateway_cmd(args))
```

- [ ] **Step 3: Register TauriPlatform in Gateway**

In `gateway/gateway.py`, no changes needed — TauriPlatform is registered in ultimate.py before Gateway.run().

- [ ] **Step 4: Verify imports**

Run: `python -c "from ultimate import _find_tauri_binary; print(_find_tauri_binary())"`
Expected: `None` (Tauri binary not built yet) — this is OK.

- [ ] **Step 5: Commit**

```bash
git add config.yaml ultimate.py
git commit -m "feat: integrate TauriPlatform into gateway command

- Add --no-gui flag to skip Tauri launch
- Auto-detect Tauri binary (project → PATH)
- Tauri subprocess lifecycle tied to gateway start/stop
- Add gui config section to config.yaml

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 4: Python — VoicePlatform Broadcast Hooks

**Files:**
- Modify: `platforms/voice/platform.py`

**Interfaces:**
- Consumes: `TauriPlatform.broadcast()` (accessed via Gateway reference)
- Produces: VoicePlatform calls broadcast at wake/stt/thinking/tts lifecycle points

- [ ] **Step 1: Read current VoicePlatform to find broadcast points**

Read `platforms/voice/platform.py` to identify where `_on_wake`, STT result, TTS start/end, and idle transitions occur. The VoicePlatform has a `_tauri_platform` attribute or receives a reference.

- [ ] **Step 2: Add tauri_platform reference and broadcast calls**

In VoicePlatform, add `tauri_platform` as an optional attribute set via `set_tauri_platform()`:

```python
# In VoicePlatform.__init__ or as a setter
self._tauri_platform = None  # set by gateway

def set_tauri_platform(self, tauri):
    self._tauri_platform = tauri

async def _broadcast(self, event: dict):
    if self._tauri_platform:
        await self._tauri_platform.broadcast(event)
```

Insert broadcast calls at lifecycle points:
- On wake detected: `await self._broadcast(wake_event())`
- After STT result: `await self._broadcast(stt_event(text))`
- Before LLM call: `await self._broadcast(thinking_event())`
- TTS start: `await self._broadcast(tts_start_event())`
- TTS end: `await self._broadcast(tts_end_event())`
- Return to listening: `await self._broadcast(idle_event())`

For `text_chunk`, VoicePlatform passes `on_text_chunk` callback to AgentRunner:

```python
on_chunk = lambda text: asyncio.create_task(
    self._broadcast(text_chunk_event(text))
)
reply = await self._runner.run_turn(
    user_input=text,
    messages=messages,
    store=store,
    on_text_chunk=on_chunk,
)
```

- [ ] **Step 3: Update ultimate.py gateway registration to wire tauri_platform**

In `ultimate.py` gateway_cmd(), after registering platforms:

```python
tauri_plat = TauriPlatform(port=18765)
voice_plat = VoicePlatform(wake_word="你好")
voice_plat.set_tauri_platform(tauri_plat)

gateway = Gateway().register(tauri_plat).register(voice_plat)
```

- [ ] **Step 4: Verify import chain**

Run: `python -c "from platforms.voice.platform import VoicePlatform; from gateway.tauri_platform import TauriPlatform; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add platforms/voice/platform.py ultimate.py
git commit -m "feat: wire VoicePlatform lifecycle events to TauriPlatform

- VoicePlatform.set_tauri_platform() for broadcast reference
- Broadcast wake, stt, thinking, tts_start, tts_end, idle events
- Wire on_text_chunk callback via AgentRunner for streaming text
- Gateway registration order ensures tauri_platform is available

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 5: Tauri — Rust Project Scaffolding

**Files:**
- Create: `ui/src-tauri/Cargo.toml`
- Create: `ui/src-tauri/tauri.conf.json`
- Create: `ui/src-tauri/src/main.rs`
- Create: `ui/src-tauri/src/ws.rs`
- Create: `ui/src-tauri/src/window.rs`
- Create: `ui/src-tauri/icons/` (placeholder icon)

**Interfaces:**
- Produces: Tauri app binary with window + WS + tray, compiled via `cargo build`

- [ ] **Step 1: Create Cargo.toml**

```toml
[package]
name = "jarvis-ui"
version = "0.1.0"
edition = "2021"

[dependencies]
tauri = { version = "1", features = ["shell-open"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio-tungstenite = "0.21"
tokio = { version = "1", features = ["full"] }
futures-util = "0.3"

[build-dependencies]
tauri-build = { version = "1", features = [] }

[build]
target = "x86_64-pc-windows-msvc"
```

- [ ] **Step 2: Create tauri.conf.json**

```json
{
  "build": {
    "distDir": "../dist",
    "devPath": "http://localhost:5173",
    "beforeDevCommand": "npm run dev",
    "beforeBuildCommand": "npm run build"
  },
  "tauri": {
    "bundle": {
      "active": true,
      "identifier": "com.ultimate.jarvis-ui",
      "icon": ["icons/32x32.png", "icons/128x128.png", "icons/icon.ico"]
    },
    "windows": [
      {
        "title": "JARVIS",
        "width": 900,
        "height": 600,
        "resizable": true,
        "decorations": false,
        "visible": false,
        "center": true,
        "skipTaskbar": false
      }
    ],
    "systemTray": {
      "iconPath": "icons/icon.ico",
      "iconAsTemplate": true
    },
    "security": {
      "csp": null
    }
  }
}
```

- [ ] **Step 3: Create main.rs skeleton**

```rust
// ui/src-tauri/src/main.rs
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod window;
mod ws;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle();
            let window = handle.get_window("main").unwrap();

            // 启动 WebSocket 连接
            let ws_url = "ws://127.0.0.1:18765/ws".to_string();
            ws::connect(ws_url, handle.clone());

            // 系统托盘
            window::setup_tray(handle.clone())?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

- [ ] **Step 4: Commit**

```bash
git add ui/
git commit -m "feat: scaffold Tauri v1 Rust project

- Cargo.toml with tauri, tokio-tungstenite, serde
- tauri.conf.json: frameless, hidden, 900x600, system tray
- main.rs: setup with WS connect + tray

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 6: Tauri Rust — WebSocket Client + Window Manager

**Files:**
- Modify: `ui/src-tauri/src/ws.rs` (full implementation)
- Modify: `ui/src-tauri/src/window.rs` (full implementation)

**Interfaces:**
- Consumes: Tauri `AppHandle`, `Window`
- Produces: `ws::connect(url, handle)` with reconnect; `window::show()`, `window::hide()`, `window::setup_tray()`

- [ ] **Step 1: Implement ws.rs**

```rust
// ui/src-tauri/src/ws.rs
use std::time::Duration;
use tauri::{AppHandle, Manager};
use tokio::time::sleep;
use tokio_tungstenite::connect_async;
use futures_util::StreamExt;

pub fn connect(url: String, handle: AppHandle) {
    tokio::spawn(async move {
        let mut retries = 0;
        let max_retries = 10;

        loop {
            match connect_async(&url).await {
                Ok((ws_stream, _)) => {
                    println!("[WS] Connected to {}", url);
                    retries = 0;
                    let (_, read) = ws_stream.split();

                    // Handle handshake — send hello
                    // (Handled separately via Sink if needed; for now just read)

                    read.for_each(|msg| {
                        if let Ok(msg) = msg {
                            if msg.is_text() || msg.is_close() {
                                if let Ok(text) = msg.to_text() {
                                    if let Ok(event) = serde_json::from_str::<serde_json::Value>(text) {
                                        let event_type = event["event"].as_str().unwrap_or("");
                                        let payload = text.to_string();
                                        match event_type {
                                            "wake" => {
                                                let win = handle.get_window("main").unwrap();
                                                let _ = win.emit("tauri://wake", &payload);
                                                window_show(&handle);
                                            }
                                            "stt" => {
                                                let _ = handle.emit_all("tauri://stt", &payload);
                                            }
                                            "thinking" => {
                                                let _ = handle.emit_all("tauri://thinking", &payload);
                                            }
                                            "text_chunk" => {
                                                let _ = handle.emit_all("tauri://text-chunk", &payload);
                                            }
                                            "data" => {
                                                let _ = handle.emit_all("tauri://data", &payload);
                                            }
                                            "amplitude" => {
                                                let _ = handle.emit_all("tauri://amplitude", &payload);
                                            }
                                            "tts_start" => {
                                                let _ = handle.emit_all("tauri://tts-start", &payload);
                                            }
                                            "tts_end" => {
                                                let _ = handle.emit_all("tauri://tts-end", &payload);
                                            }
                                            "idle" => {
                                                let _ = handle.emit_all("tauri://idle", &payload);
                                                start_hide_timer(&handle);
                                            }
                                            "error" => {
                                                let _ = handle.emit_all("tauri://error", &payload);
                                            }
                                            _ => {}
                                        }
                                    }
                                }
                            }
                        }
                        futures_util::future::ready(())
                    }).await;
                }
                Err(e) => {
                    println!("[WS] Connection failed: {}", e);
                }
            }

            // 重连退避
            if retries >= max_retries {
                println!("[WS] Max retries reached, giving up");
                break;
            }
            retries += 1;
            let delay = Duration::from_millis(std::cmp::min(500 * 2u64.pow(retries), 10000));
            println!("[WS] Reconnecting in {:?} (attempt {}/{})", delay, retries, max_retries);
            sleep(delay).await;
        }
    });
}

use crate::window::{show as window_show, start_hide_timer};
```

- [ ] **Step 2: Implement window.rs**

```rust
// ui/src-tauri/src/window.rs
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Manager, SystemTray, SystemTrayMenu, SystemTrayMenuItem, CustomMenuItem, SystemTrayEvent};
use tokio::time::sleep;

static HIDE_TIMER_ACTIVE: Mutex<bool> = Mutex::new(false);

pub fn show(handle: &AppHandle) {
    if let Some(window) = handle.get_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

pub fn hide(handle: &AppHandle) {
    if let Some(window) = handle.get_window("main") {
        let _ = window.hide();
    }
}

pub fn start_hide_timer(handle: &AppHandle) {
    // 检查是否已有定时器运行
    {
        let mut active = HIDE_TIMER_ACTIVE.lock().unwrap();
        if *active {
            return;
        }
        *active = true;
    }

    let handle_clone = handle.clone();
    tokio::spawn(async move {
        sleep(Duration::from_secs(10)).await;

        *HIDE_TIMER_ACTIVE.lock().unwrap() = false;

        // 再次检查：如果窗口仍然是可见的（没有被新事件打断）
        if let Some(window) = handle_clone.get_window("main") {
            if window.is_visible().unwrap_or(false) {
                hide(&handle_clone);
            }
        }
    });
}

pub fn cancel_hide_timer() {
    *HIDE_TIMER_ACTIVE.lock().unwrap() = false;
}

pub fn setup_tray(handle: AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let show = CustomMenuItem::new("show".to_string(), "显示/隐藏窗口");
    let quit = CustomMenuItem::new("quit".to_string(), "退出");

    let menu = SystemTrayMenu::new()
        .add_item(show)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit);

    let tray = SystemTray::new().with_menu(menu);

    let handle_clone = handle.clone();
    tray.on_event(move |event| match event {
        SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
            "show" => {
                if let Some(window) = handle_clone.get_window("main") {
                    if window.is_visible().unwrap_or(false) {
                        hide(&handle_clone);
                    } else {
                        show(&handle_clone);
                    }
                }
            }
            "quit" => {
                handle_clone.exit(0);
            }
            _ => {}
        },
        _ => {}
    });

    handle.tray_handle().set_tray(tray)?;
    Ok(())
}
```

- [ ] **Step 3: Verify compilation**

Run: `cd ui && cargo check 2>&1`
Expected: Compilation succeeds (may need `cargo install tauri-cli` first, or just `cargo check` in src-tauri)

- [ ] **Step 4: Commit**

```bash
git add ui/src-tauri/src/ws.rs ui/src-tauri/src/window.rs ui/src-tauri/src/main.rs
git commit -m "feat: implement Rust WS client and window manager

- WebSocket client with exponential backoff reconnect
- WS message → Tauri event dispatch for all event types
- Frameless window show/hide + 10s idle auto-hide
- System tray with show/hide toggle and quit

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 7: Vue3 — Project Scaffolding + JARVIS Theme

**Files:**
- Create: `ui/package.json`
- Create: `ui/vite.config.ts`
- Create: `ui/tsconfig.json`
- Create: `ui/index.html`
- Create: `ui/src/main.ts`
- Create: `ui/src/types/events.ts`
- Create: `ui/src/assets/styles/jarvis-theme.css`

**Interfaces:**
- Produces: Vue3 dev server on :5173, JARVIS CSS custom properties

- [ ] **Step 1: Create package.json**

```json
{
  "name": "jarvis-ui",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc --noEmit && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "@tauri-apps/api": "^1.5.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vue-tsc": "^1.8.0"
  }
}
```

- [ ] **Step 2: Create vite.config.ts, tsconfig.json, index.html**

Standard Tauri + Vue3 setup. Vite config with `@vitejs/plugin-vue`. index.html mounts `#app`.

- [ ] **Step 3: Create main.ts entry**

```typescript
// ui/src/main.ts
import { createApp } from 'vue'
import App from './App.vue'
import './assets/styles/jarvis-theme.css'

createApp(App).mount('#app')
```

- [ ] **Step 4: Create events.ts types**

```typescript
// ui/src/types/events.ts
export interface WakeEvent { event: 'wake' }
export interface SttEvent { event: 'stt'; text: string }
export interface ThinkingEvent { event: 'thinking' }
export interface TextChunkEvent { event: 'text_chunk'; text: string }
export interface DataEvent { event: 'data'; type: 'table'; columns: string[]; rows: any[][] }
export interface AmplitudeEvent { event: 'amplitude'; rms: number }
export interface TtsStartEvent { event: 'tts_start' }
export interface TtsEndEvent { event: 'tts_end' }
export interface IdleEvent { event: 'idle' }
export interface ErrorEvent { event: 'error'; reason: string }

export type BackendEvent = WakeEvent | SttEvent | ThinkingEvent | TextChunkEvent |
  DataEvent | AmplitudeEvent | TtsStartEvent | TtsEndEvent | IdleEvent | ErrorEvent

export interface Message {
  id: number
  role: 'user' | 'agent'
  text: string
  isStreaming: boolean
  isInterrupted: boolean
}

export type UiMode = 'hidden' | 'waveform' | 'thinking' | 'conversing' | 'showingData'
export type WaveformMode = 'breath' | 'pulsate' | 'pulse' | 'active'
```

- [ ] **Step 5: Create jarvis-theme.css**

```css
/* ui/src/assets/styles/jarvis-theme.css */
:root {
  --bg-primary: #0a0a1a;
  --bg-panel: rgba(20, 30, 60, 0.6);
  --accent: #00d4ff;
  --accent-dim: rgba(0, 212, 255, 0.3);
  --text: #e0e8ff;
  --text-dim: rgba(200, 210, 240, 0.6);
  --border-glow: 0 0 10px rgba(0, 212, 255, 0.5);
  --font-mono: 'Consolas', 'Courier New', monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html, body, #app {
  width: 100%; height: 100%;
  background: var(--bg-primary);
  color: var(--text);
  font-family: var(--font-mono);
  overflow: hidden;
  user-select: none;
}

.panel {
  background: var(--bg-panel);
  backdrop-filter: blur(8px);
  border: 1px solid var(--accent-dim);
  border-radius: 8px;
  box-shadow: var(--border-glow);
}

.fade-enter-active { transition: opacity 0.3s ease; }
.fade-leave-active { transition: opacity 0.5s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.slide-up-enter-active { transition: all 0.3s ease; }
.slide-up-leave-active { transition: all 0.3s ease; }
.slide-up-enter-from, .slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

.drag-region {
  -webkit-app-region: drag;
  cursor: grab;
}
```

- [ ] **Step 6: Verify dev server**

Run: `cd ui && npm install && npm run dev` (verify it starts, then Ctrl-C)

- [ ] **Step 7: Commit**

```bash
git add ui/package.json ui/vite.config.ts ui/tsconfig.json ui/index.html ui/src/main.ts ui/src/types/events.ts ui/src/assets/styles/jarvis-theme.css
git commit -m "feat: scaffold Vue3 project with JARVIS theme

- Vue3 + TypeScript + Vite with @tauri-apps/api
- Event type definitions for all WS events
- JARVIS dark theme CSS (custom properties, panels, transitions)
- Frameless drag region support

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 8: Vue3 — Composable + Waveform Component

**Files:**
- Create: `ui/src/composables/useTauriEvents.ts`
- Create: `ui/src/components/JarvisWaveform.vue`

**Interfaces:**
- Consumes: Tauri event system (`@tauri-apps/api/event`)
- Produces: `useTauriEvents()` reactive state; `JarvisWaveform` with `mode` and `amplitude` props

- [ ] **Step 1: Create useTauriEvents.ts**

```typescript
// ui/src/composables/useTauriEvents.ts
import { reactive } from 'vue'
import { listen } from '@tauri-apps/api/event'
import type { Message, UiMode, WaveformMode } from '../types/events'

export function useTauriEvents() {
  const state = reactive({
    uiMode: 'hidden' as UiMode,
    waveformMode: 'breath' as WaveformMode,
    amplitude: 0,
    messages: [] as Message[],
    messageIdCounter: 0,
    currentStreamingId: -1,
    tableData: null as { columns: string[]; rows: any[][] } | null,
    tableVisible: false,
  })

  async function setupListeners() {
    await listen<string>('tauri://wake', () => {
      state.uiMode = 'waveform'
      state.waveformMode = 'pulsate'
    })

    await listen<string>('tauri://stt', (e) => {
      const payload = JSON.parse(e.payload)
      state.messages.push({
        id: ++state.messageIdCounter, role: 'user',
        text: payload.text, isStreaming: false, isInterrupted: false
      })
      state.uiMode = 'thinking'
      state.waveformMode = 'pulse'
    })

    await listen<string>('tauri://thinking', () => {
      state.uiMode = 'thinking'
      state.waveformMode = 'pulse'
    })

    await listen<string>('tauri://text-chunk', (e) => {
      const payload = JSON.parse(e.payload)
      if (state.uiMode !== 'conversing' && state.uiMode !== 'showingData') {
        state.uiMode = 'conversing'
      }

      if (state.currentStreamingId < 0) {
        // First chunk: create new streaming message
        state.currentStreamingId = ++state.messageIdCounter
        state.messages.push({
          id: state.currentStreamingId, role: 'agent',
          text: payload.text, isStreaming: true, isInterrupted: false
        })
      } else {
        // Append to existing streaming message
        const msg = state.messages.find(m => m.id === state.currentStreamingId)
        if (msg) msg.text += payload.text
      }
    })

    await listen<string>('tauri://data', (e) => {
      const payload = JSON.parse(e.payload)
      state.tableData = { columns: payload.columns, rows: payload.rows }
      state.tableVisible = true
      state.uiMode = 'showingData'
    })

    await listen<string>('tauri://amplitude', (e) => {
      const payload = JSON.parse(e.payload)
      state.amplitude = payload.rms
    })

    await listen<string>('tauri://tts-start', () => {
      state.waveformMode = 'active'
    })

    await listen<string>('tauri://tts-end', () => {
      state.waveformMode = 'breath'
    })

    await listen<string>('tauri://idle', () => {
      // Mark current streaming as done
      state.currentStreamingId = -1
      state.waveformMode = 'breath'
    })

    await listen<string>('tauri://error', (e) => {
      const payload = JSON.parse(e.payload)
      if (state.currentStreamingId >= 0) {
        const msg = state.messages.find(m => m.id === state.currentStreamingId)
        if (msg) msg.isInterrupted = true
        state.currentStreamingId = -1
      }
    })
  }

  // Call setup immediately
  setupListeners()

  return { state }
}
```

- [ ] **Step 2: Create JarvisWaveform.vue**

```vue
<!-- ui/src/components/JarvisWaveform.vue -->
<template>
  <canvas ref="canvasRef" class="waveform-canvas" :width="size" :height="size"></canvas>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import type { WaveformMode } from '../types/events'

const props = defineProps<{
  mode: WaveformMode
  amplitude: number
  size?: number
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let animFrameId = 0
let phase = 0

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const s = props.size || 300
  const cx = s / 2, cy = s / 2

  ctx.clearRect(0, 0, s, s)

  const rings = [
    { r: 60, opacity: 0.15 },
    { r: 80, opacity: 0.25 },
    { r: 100, opacity: 0.35 },
  ]

  let scale = 1.0
  if (props.mode === 'pulsate') {
    scale = 1.0 + props.amplitude * 0.4 + Math.sin(phase * 2) * 0.05
  } else if (props.mode === 'pulse') {
    scale = 1.0 + Math.sin(phase * 0.8) * 0.08
  } else if (props.mode === 'active') {
    scale = 1.0 + Math.sin(phase * 3) * 0.12
  } else {
    // breath
    scale = 1.0 + Math.sin(phase * 0.3) * 0.02
  }

  for (const ring of rings) {
    const r = ring.r * scale
    ctx.beginPath()
    ctx.arc(cx, cy, r, 0, Math.PI * 2)
    ctx.strokeStyle = `rgba(0, 212, 255, ${ring.opacity})`
    ctx.lineWidth = 1.5
    ctx.stroke()
  }

  // 动态正弦波环（最内层）
  const waveR = 45 * scale
  ctx.beginPath()
  const points = 120
  for (let i = 0; i <= points; i++) {
    const angle = (i / points) * Math.PI * 2
    const distortion = props.mode === 'pulsate'
      ? props.amplitude * 15 * Math.sin(angle * 3 + phase)
      : Math.sin(angle * 5 + phase) * 5
    const r = waveR + distortion
    const x = cx + Math.cos(angle) * r
    const y = cy + Math.sin(angle) * r
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  }
  ctx.closePath()
  ctx.strokeStyle = '#00d4ff'
  ctx.lineWidth = 2
  ctx.shadowColor = 'rgba(0, 212, 255, 0.6)'
  ctx.shadowBlur = 12
  ctx.stroke()
  ctx.shadowBlur = 0

  // 中心光点
  ctx.beginPath()
  ctx.arc(cx, cy, 4, 0, Math.PI * 2)
  ctx.fillStyle = '#00d4ff'
  ctx.shadowColor = 'rgba(0, 212, 255, 0.8)'
  ctx.shadowBlur = 15
  ctx.fill()
  ctx.shadowBlur = 0

  phase += 0.05
  animFrameId = requestAnimationFrame(draw)
}

onMounted(() => { draw() })
onUnmounted(() => { cancelAnimationFrame(animFrameId) })
</script>

<style scoped>
.waveform-canvas {
  display: block;
  margin: 0 auto;
}
</style>
```

- [ ] **Step 3: Verify compilation**

Run: `cd ui && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add ui/src/composables/useTauriEvents.ts ui/src/components/JarvisWaveform.vue
git commit -m "feat: add useTauriEvents composable and JarvisWaveform

- useTauriEvents: reactive state driven by Tauri event listeners
- Progressive reveal state machine (hidden→waveform→thinking→conversing)
- JarvisWaveform: Canvas 2D ring waveform with 4 modes
- 60fps rAF loop with smooth mode transitions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 9: Vue3 — Conversation + InputBar + DataTable

**Files:**
- Create: `ui/src/components/ConversationView.vue`
- Create: `ui/src/components/MessageBubble.vue`
- Create: `ui/src/components/InputBar.vue`
- Create: `ui/src/components/DataTable.vue`

- [ ] **Step 1: Create MessageBubble.vue**

```vue
<template>
  <div :class="['bubble', role, { interrupted: isInterrupted, streaming: isStreaming }]">
    <div class="role-label">{{ role === 'user' ? 'YOU' : 'LUNA' }}</div>
    <div class="bubble-text">{{ text }}<span v-if="isStreaming" class="cursor">▊</span></div>
    <div v-if="isInterrupted" class="interrupted-badge">⚡ 连接中断</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  role: 'user' | 'agent'
  text: string
  isStreaming: boolean
  isInterrupted: boolean
}>()
</script>

<style scoped>
.bubble { margin-bottom: 12px; }
.role-label { font-size: 10px; color: var(--text-dim); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 1px; }
.bubble-text { padding: 10px 14px; border-radius: 6px; font-size: 13px; line-height: 1.5; }
.user .bubble-text { background: rgba(0,212,255,0.08); color: var(--text); }
.agent .bubble-text { background: rgba(0,212,255,0.04); color: var(--accent); }
.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
.interrupted-badge { font-size: 11px; color: #ff6b6b; margin-top: 4px; }
.interrupted .bubble-text { border: 1px solid rgba(255,107,107,0.3); }
</style>
```

- [ ] **Step 2: Create InputBar.vue**

```vue
<template>
  <div v-if="visible" class="input-bar">
    <input
      ref="inputRef"
      v-model="text"
      class="text-input"
      placeholder="输入消息..."
      @keydown.enter="send"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { invoke } from '@tauri-apps/api/tauri'

const props = defineProps<{ visible: boolean }>()
const text = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

watch(() => props.visible, (v) => {
  if (v) setTimeout(() => inputRef.value?.focus(), 100)
})

function send() {
  if (!text.value.trim()) return
  invoke('send_input', { text: text.value })
  text.value = ''
}
</script>

<style scoped>
.input-bar { padding: 10px 0; }
.text-input {
  width: 100%; padding: 10px 14px;
  background: rgba(0,212,255,0.06); border: 1px solid var(--accent-dim);
  border-radius: 6px; color: var(--text); font-family: var(--font-mono);
  font-size: 13px; outline: none;
}
.text-input:focus { border-color: var(--accent); box-shadow: var(--border-glow); }
.text-input::placeholder { color: var(--text-dim); }
</style>
```

- [ ] **Step 3: Create ConversationView.vue**

```vue
<template>
  <div v-if="conversationVisible" class="conversation-view panel">
    <div class="conv-header">对话</div>
    <div class="conv-messages" ref="scrollRef">
      <MessageBubble v-for="msg in messages" :key="msg.id"
        :role="msg.role" :text="msg.text"
        :isStreaming="msg.isStreaming" :isInterrupted="msg.isInterrupted"
      />
    </div>
    <InputBar :visible="inputVisible" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import MessageBubble from './MessageBubble.vue'
import InputBar from './InputBar.vue'
import type { Message } from '../types/events'

const props = defineProps<{
  messages: Message[]
  visible: boolean
}>()

const scrollRef = ref<HTMLElement | null>(null)
const conversationVisible = computed(() => props.visible && props.messages.length > 0)
const inputVisible = computed(() => conversationVisible.value)

watch(() => props.messages.length, async () => {
  await nextTick()
  if (scrollRef.value) {
    scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  }
})
</script>

<style scoped>
.conversation-view {
  padding: 12px;
  display: flex; flex-direction: column;
  max-height: 300px; min-height: 120px;
}
.conv-header {
  font-size: 10px; color: var(--text-dim); text-transform: uppercase;
  letter-spacing: 1px; margin-bottom: 8px;
}
.conv-messages {
  flex: 1; overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--accent-dim) transparent;
}
</style>
```

- [ ] **Step 4: Create DataTable.vue**

```vue
<template>
  <Transition name="fade">
    <div v-if="visible" class="data-table panel">
      <div class="table-header">
        <span>DATA</span>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>
      <table>
        <thead>
          <tr><th v-for="col in columns" :key="col">{{ col }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in rows" :key="i">
            <td v-for="(cell, j) in row" :key="j">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </Transition>
</template>

<script setup lang="ts">
defineProps<{
  columns: string[]
  rows: any[][]
  visible: boolean
}>()
defineEmits(['close'])
</script>

<style scoped>
.data-table { padding: 12px; margin-top: 10px; }
.table-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
.close-btn { background: none; border: 1px solid var(--accent-dim); color: var(--accent); cursor: pointer; border-radius: 4px; padding: 2px 8px; font-size: 12px; }
.close-btn:hover { background: rgba(0,212,255,0.1); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: left; padding: 6px 10px; border-bottom: 2px solid var(--accent-dim); color: var(--accent); }
td { padding: 5px 10px; border-bottom: 1px solid rgba(0,212,255,0.08); color: var(--text); }
tr:nth-child(even) td { background: rgba(0,212,255,0.03); }
</style>
```

- [ ] **Step 5: Commit**

```bash
git add ui/src/components/
git commit -m "feat: add ConversationView, MessageBubble, InputBar, DataTable

- MessageBubble with streaming cursor and interrupted badge
- InputBar with keyboard text input (enter to send)
- ConversationView with auto-scroll and slide-in animation
- DataTable with JARVIS themed table and close button

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 10: Vue3 — App.vue Root Component

**Files:**
- Create: `ui/src/App.vue`

- [ ] **Step 1: Create App.vue**

```vue
<template>
  <div class="app-root" data-tauri-drag-region>
    <!-- Drag region header -->
    <div class="drag-header" data-tauri-drag-region>
      <span class="status-text">{{ statusText }}</span>
      <button class="close-btn" @click="onClose">✕</button>
    </div>

    <!-- Waveform — always visible when uiMode != 'hidden' -->
    <Transition name="fade">
      <div v-if="state.uiMode !== 'hidden'" class="waveform-container">
        <JarvisWaveform :mode="state.waveformMode" :amplitude="state.amplitude" :size="260" />
        <div class="mode-label">{{ modeLabel }}</div>
      </div>
    </Transition>

    <!-- Conversation — slide up on conversing/showingData -->
    <Transition name="slide-up">
      <ConversationView
        v-if="state.uiMode === 'conversing' || state.uiMode === 'showingData'"
        :messages="state.messages"
        :visible="true"
      />
    </Transition>

    <!-- Data Table — fade in -->
    <Transition name="fade">
      <DataTable
        v-if="state.tableVisible && state.tableData"
        :columns="state.tableData.columns"
        :rows="state.tableData.rows"
        :visible="state.tableVisible"
        @close="state.tableVisible = false"
      />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import JarvisWaveform from './components/JarvisWaveform.vue'
import ConversationView from './components/ConversationView.vue'
import DataTable from './components/DataTable.vue'
import { useTauriEvents } from './composables/useTauriEvents'

const { state } = useTauriEvents()

const statusText = computed(() => {
  switch (state.uiMode) {
    case 'hidden': return '◉ JARVIS Online'
    case 'waveform': return '🎤 Listening...'
    case 'thinking': return '◉ Thinking...'
    case 'conversing': return '◉ Responding'
    case 'showingData': return '◉ Data'
    default: return '◉ JARVIS'
  }
})

const modeLabel = computed(() => {
  switch (state.waveformMode) {
    case 'breath': return '待命中'
    case 'pulsate': return '聆听中'
    case 'pulse': return '思考中'
    case 'active': return '回复中'
    default: return ''
  }
})

function onClose() {
  // Send close event, then hide (don't quit — stay in tray)
  import('@tauri-apps/api/tauri').then(({ invoke }) => invoke('close_window'))
}
</script>

<style scoped>
.app-root {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  background: linear-gradient(135deg, #0a0a1a 0%, #0d0d2b 50%, #0a0a1a 100%);
  padding: 16px;
}

.drag-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 0 12px;
}
.status-text { font-size: 12px; color: var(--text-dim); letter-spacing: 2px; }
.close-btn {
  background: none; border: 1px solid rgba(255,255,255,0.1); color: var(--text-dim);
  cursor: pointer; border-radius: 50%; width: 24px; height: 24px; font-size: 12px;
  -webkit-app-region: no-drag;
}
.close-btn:hover { color: var(--accent); border-color: var(--accent-dim); }

.waveform-container {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}
.mode-label {
  font-size: 11px; color: var(--text-dim); margin-top: 8px;
  letter-spacing: 1px; text-transform: uppercase;
}
</style>
```

- [ ] **Step 2: Add Rust invoke handler for close_window**

In `ui/src-tauri/src/main.rs`, add:

```rust
#[tauri::command]
fn close_window(window: tauri::Window) {
    let _ = window.hide();
}

// In main():
.manage(...)
.invoke_handler(tauri::generate_handler![close_window])
```

Also add the `send_input` command to forward keyboard input to WS. The Rust WS client module needs a way to send messages. Add a simple static channel or use Tauri state.

For simplicity, add a `send_input` command that emits a custom event back to the WS loop:

```rust
#[tauri::command]
fn send_input(text: String, handle: tauri::AppHandle) {
    // Forward to WS via a channel — for now, log and emit locally
    println!("[Input] {}", text);
    let _ = handle.emit_all("tauri://user-input", &text);
}
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/App.vue ui/src-tauri/src/main.rs
git commit -m "feat: add App.vue root component with progressive reveal

- Drag-region header with status text and close button
- Waveform always visible when UI is active
- Conversation slides up on conversing/showingData
- Data table fades in as overlay
- Rust commands: close_window, send_input

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-jarvis-desktop-gui
---

### Task 11: Integration & Manual Testing

- [ ] **Step 1: Start Python backend**

Run: `python ultimate.py gateway --no-gui`
Expected: Gateway starts, VoicePlatform begins listening. WS server on :18765.

- [ ] **Step 2: Start Tauri dev mode**

Run: `cd ui && npm run dev` (Terminal 1)
Then: `cd ui/src-tauri && cargo run` (Terminal 2)

- [ ] **Step 3: Test full flow**

1. Say wake word "你好" → window should appear with waveform
2. Speak a command → waveform pulsates, text appears
3. Agent replies → streaming text in conversation area
4. Idle 10s → window fades and hides
5. Click tray icon → window toggles

- [ ] **Step 4: Fix issues and final commit**

```bash
git add -A
git commit -m "chore: integration fixes and final adjustments

Co-Authored-By: Claude <noreply@anthropic.com>"
```
