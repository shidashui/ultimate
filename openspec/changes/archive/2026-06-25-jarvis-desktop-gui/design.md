## Context

Ultimate Agent 目前通过 CLI (`ultimate.py chat`) 和 Gateway (`ultimate.py gateway`) 两种方式交互。Gateway 模式支持多平台注册（VoicePlatform、WeChatPlatform），但缺少桌面端可视化界面。

VoicePlatform 已实现两阶段唤醒（Silero VAD → Whisper 唤醒词检测）→ STT → LLM → TTS 的完整语音交互链路，但整个过程完全在后台运行，用户没有任何视觉反馈。

本项目在保持现有 VoicePlatform 核心链路不变的前提下，新增 Tauri + Vue3 桌面端应用作为 Agent 的视觉交互层。

## Goals / Non-Goals

### Goals
- Tauri 桌面应用被 Gateway 启动后隐藏在系统托盘，唤醒词触发时弹出 JARVIS 风格窗口
- Vue3 前端实时渲染：动态音频波形、流式对话文本、结构化数据表格
- Python 后端通过 WebSocket 推送 VoicePlatform 生命周期事件（唤醒→STT→thinking→TTS→空闲）
- 用户可通过语音或键盘输入与 Agent 交互，GUI 同步展示 Agent 状态和回复
- Tauri Rust 层管理窗口生命周期（显示/隐藏/渐变动画）和系统托盘

### Non-Goals
- 不修改 VoicePlatform 的唤醒词检测、STT、TTS 核心算法
- 不修改 WeChatPlatform
- 不支持多显示器环境的首选屏幕选择
- 不涉及语音唤醒词模型的更换（仍使用 Silero VAD + Whisper）
- 不实现视频/动画 Avatar（纯 UI 组件风格）

## Decisions

### D1: Gateway 进程管理 Tauri 子进程

**方案**：`ultimate.py gateway` 通过 `subprocess.Popen` 启动 Tauri 二进制。

```python
# gateway 命令逻辑
def gateway_cmd():
    # 1. 启动 Tauri 进程（除非 --no-gui）
    tauri_process = None
    if not args.no_gui:
        tauri_bin = find_tauri_binary()
        tauri_process = subprocess.Popen([tauri_bin])
    
    # 2. 注册平台
    gateway = Gateway()
    gateway.register(TauriPlatform(port=18765))
    gateway.register(VoicePlatform(wake_word="你好"))
    
    # 3. 运行 Gateway（Tauri 连接 WS 后自动工作）
    asyncio.run(gateway.run())
```

**备选方案**：用户手动双击 Tauri 应用 → 作为纯 GUI 客户端连后端。弃用理由：增加用户操作步骤，且需要 Tauri 内置发现后端地址的逻辑。子进程方案更一体化。

**权衡**：Python 进程退出时需 kill Tauri 子进程。Gateway 的 shutdown 钩子中处理 `tauri_process.terminate()`。

### D2: Tauri Rust 层持有 WebSocket 客户端（非 Vue3 直连）

**方案**：Tauri Rust 层通过 `tokio-tungstenite` 建立 WebSocket 连接到 `ws://127.0.0.1:18765`。Vue3 通过 Tauri `invoke()` 和 `emit()` 与 Rust 通信。

```
Vue3 (UI 渲染)
    │ invoke / events
    ▼
Tauri Rust (WS 客户端 + 窗口管理)
    │ WebSocket
    ▼
Python (aiohttp WS Server)
```

**理由**：
- 窗口生命周期（show/hide/fade）由 Rust 控制，Vue3 层只需响应 `@tauri-apps/api/window`
- Rust 作为 WS 客户端可以管理重连逻辑（Python 后端重启时自动重连）
- Vue3 侧避免直接管理原始 WebSocket，减少前端复杂度

**事件流**：
```
// Rust → Vue3 (tauri event emit)
"tauri://wake"          → 窗口弹出 + 启动波形
"tauri://stt"           → 显示识别文本
"tauri://thinking"      → 显示思考状态
"tauri://text-chunk"    → 流式追加对话文本
"tauri://data"          → 渲染结构化数据
"tauri://tts-start"     → 显示 TTS 状态
"tauri://idle"          → N 秒后窗口淡出

// Vue3 → Rust (tauri invoke/event)
"tauri://input-text"    → 用户键盘输入 → Rust WS 转发
"tauri://close"         → 用户主动关闭 → Rust hide 窗口
```

### D3: 后端事件广播机制

**方案**：TauriPlatform 作为一个事件广播通道（而非传统消息平台），提供 `broadcast()` 方法供 VoicePlatform 及其他模块推送状态事件。

```python
class TauriPlatform(BasePlatform):
    platform_name = "tauri"
    channel = "desktop"
    
    def __init__(self, port=18765):
        self.port = port
        self.connections: set[WebSocketResponse] = set()
    
    async def broadcast(self, event: dict):
        """广播事件给所有连接的 Tauri 客户端"""
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_json(event)
            except ConnectionError:
                dead.add(ws)
        self.connections -= dead
```

VoicePlatform 在生命周期关键点调用 `tauri_platform.broadcast()`：

```python
# VoicePlatform 改造点
async def _on_wake_detected(self):
    await self.tauri_platform.broadcast({"event": "wake"})
    # ... 原有唤醒逻辑

async def _on_stt_result(self, text: str):
    await self.tauri_platform.broadcast({"event": "stt", "text": text})
    # ... 原有 STT 逻辑

async def run_turn(self, user_input: str):
    await self.tauri_platform.broadcast({"event": "thinking"})
    reply = await self.runner.run_turn(...)
    await self.tauri_platform.broadcast({"event": "text_chunk", "text": reply})
```

### D4: Vue3 前端架构

**方案**：使用 Vue3 + Vite + TypeScript，UI 组件库使用 Naive UI（按需引入，树摇优化）。

```
ui/
├── src-tauri/          # Rust 层
│   ├── src/
│   │   ├── main.rs     # 应用入口 + 系统托盘
│   │   ├── window.rs   # 窗口管理 (show/hide/fade)
│   │   └── ws.rs       # WebSocket 客户端
│   ├── Cargo.toml
│   └── tauri.conf.json
├── src/                # Vue3 前端
│   ├── App.vue          # 根组件
│   ├── main.ts          # 入口
│   ├── components/
│   │   ├── Waveform.vue      # 动态音频波形 (Canvas)
│   │   ├── Conversation.vue  # 对话流式渲染
│   │   ├── DataTable.vue     # 结构化数据表格
│   │   ├── StatusBar.vue     # 状态栏 (录音中/思考中/播放中)
│   │   └── InputBar.vue      # 键盘输入区域 (可选)
│   ├── composables/
│   │   └── useTauriEvents.ts # Tauri 事件监听封装
│   ├── types/
│   │   └── events.ts         # 事件类型定义
│   └── assets/
│       └── styles/
│           └── jarvis-theme.css  # JARVIS 全息主题
├── package.json
├── vite.config.ts
└── tsconfig.json
```

**组件树**：
```
App.vue
├── Waveform.vue          ← 居中，always visible when active
├── StatusBar.vue         ← 顶部状态 (Listening / Processing / Speaking)
├── Conversation.vue      ← 右侧/底部，对话历史列表
│   ├── MessageBubble.vue ← 用户消息
│   ├── MessageBubble.vue ← Agent 流式回复
│   └── DataTable.vue     ← 结构化数据嵌入
└── InputBar.vue          ← 底部文本输入框 (可选折叠)
```

### D5: 波形渲染方案

**方案**：使用 Canvas 2D API，通过 `requestAnimationFrame` 驱动动画。波形数据来自 Web Audio API 的 `AnalyserNode`。

实际音频来自麦克风或播放的 TTS 音频，通过 `AudioContext.createMediaStreamSource()` 或 `createBufferSource()` 获取实时频域数据。

波形风格：JARVIS 环形脉冲样式。

```
波形模式切换：
├── idle: 微弱呼吸光晕 (无音频输入)
├── listening: 环形波纹跟随语音输入振幅 pulsate
├── thinking: 缓慢脉冲 (等待回复)
└── speaking: 跟随 TTS 音频输出跳动的活跃波形
```

### D6: JARVIS 视觉主题

**方案**：纯 CSS 实现全息风格，不使用 Three.js 或 WebGL 粒子（减少包体积）。

```
Color Palette:
  --bg-primary:    #0a0a1a    (深空蓝黑)
  --bg-panel:      rgba(20, 30, 60, 0.6)  (半透明面板)
  --accent:        #00d4ff    (贾维斯蓝色)
  --accent-dim:    rgba(0, 212, 255, 0.3)
  --text:          #e0e8ff    (淡蓝白)
  --text-dim:      rgba(200, 210, 240, 0.6)
  --border-glow:   0 0 10px rgba(0, 212, 255, 0.5)

视觉层次:
  · 背景: 深色渐变 + 微弱网格线 (科技感)
  · 面板: 半透明毛玻璃 (backdrop-filter: blur)
  · 边框: 发光线条 (box-shadow + border + 微动画)
  · 波形: 中心环形, cyan->blue 渐变
  · 字体: 等宽 + 轻微发光
```

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| Tauri 子进程启动顺序：Tauri 启动可能快于 Python WS Server，连接失败 | Rust WS 客户端实现指数退避重连（最多 10 次，间隔 500ms→10s） |
| Python 进程退出时 Tauri 进程未清理 | Gateway shutdown 钩子中 `process.terminate()`，超时后 `kill()` |
| Tauri 二进制文件体积（含 WebView） | Tauri 本身 ~5MB，不打包 webview（用系统 WebView2），最终二进制预计 10-15MB |
| Windows WebView2 兼容性 | Windows 11 内置 WebView2；Windows 10 需检测并引导安装（或静默安装） |
| aiohttp WS Server 端口冲突 | 默认 18765，支持 `config.yaml` 中 `gui.ws_port` 配置，Tauri 启动时读取配置 |
| 唤醒后窗口弹出延迟 | WS 通信延迟预计 <50ms（localhost），Tauri `window.show()` 是原生操作，总延迟 <200ms，可接受 |
| 前端打包后热更新困难 | Tauri 开发模式 `trunk dev` 支持 HMR；生产版本打包为独立二进制 |
| 音频采集竞争（VoicePlatform 和浏览器都在用麦克风） | 本方案中麦克风仅由 VoicePlatform (Python) 占用；Tauri 不做音频采集，仅展示波形数据 |

## Open Questions

- Tauri 窗口样式：frameless（无边框）还是保留系统标题栏？frameless 需要在 Rust 层实现自绘标题栏和拖拽区域
- Tauri 窗口尺寸和位置：是否支持用户配置（`config.yaml` 中 `gui.window`）
- `--no-gui` 标志：只在 Gateway 模式下有意义，Chat/CLI 模式自动忽略
