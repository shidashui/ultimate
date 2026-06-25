# Comet Design Handoff

- Change: jarvis-desktop-gui
- Phase: design
- Mode: compact
- Context hash: fdf520d4fba101cb6da16b5f2cb505d02a9c388947336c1bbf14bbde9208c617

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/jarvis-desktop-gui/proposal.md

- Source: openspec/changes/jarvis-desktop-gui/proposal.md
- Lines: 1-42
- SHA256: 6a88c79e62ee5aab78d62ec374c1b1febe78f54f4584bcba8b1bd09b62670dd8

```md
## Why

Ultimate Agent 目前只有终端 CLI 和多平台消息网关（微信/语音）作为交互方式，缺少一个直观的桌面端可视化界面。用户希望在语音唤醒 Agent 后，能看到类似钢铁侠中 JARVIS 风格的全息交互窗口——动态音频波形、流式对话展示、结构化数据（表格）渲染。这个 GUI 将大幅提升与 Agent 交互的沉浸感和信息获取效率。

## What Changes

- 新建 Tauri + Vue3 桌面 GUI 应用（`ui/` 目录）
- 新增 Python 端 `TauriPlatform`（aiohttp WebSocket Server），作为 Gateway 的一个平台注册
- `gateway` 命令启动时通过 `subprocess.Popen` 自动拉起 Tauri App
- 定义并实现 Tauri ↔ Python 之间的 JSON 事件协议
- VoicePlatform 增加事件广播能力，唤醒/STT/thinking/TTS 等状态实时推送到 GUI
- Vue3 前端实现：动态音频波形（Canvas + Web Audio API）、流式对话渲染、结构化数据表格展示、JARVIS 风格全息视觉主题
- Tauri Rust 层：窗口生命周期管理（show/hide/fade）、系统托盘、WebSocket 客户端
- Gateway 的 CLI 入口支持 `--no-gui` 标志，可禁用 GUI 启动（纯 gateway 模式）

## Capabilities

### New Capabilities
- `desktop-ui`: Tauri + Vue3 桌面 GUI 应用，包含窗口管理、系统托盘、JARVIS 风格全息 UI、动态波形、对话展示、数据表格渲染
- `desktop-protocol`: Python 后端与 Tauri 前端之间的 WebSocket 实时通信协议，定义事件类型、数据格式和流式传输规范

### Modified Capabilities
- `voice-core`: 增加 GUI 事件广播接口，VoicePlatform 在唤醒/STT/LLM 回复/TTS 等关键生命周期点推送到 TauriPlatform

## Impact

- **新增依赖**：
  - 开发依赖：Rust toolchain (rustc, cargo), Node.js, npm/pnpm, Tauri CLI
  - 运行时依赖：WebView2 (Windows 内置), Tauri binary (打包后独立)
  - Python 端：aiohttp 已安装，无需新增
- **新增目录**：`ui/` — Tauri + Vue3 项目目录
- **新增文件**：
  - `ui/src-tauri/` — Tauri Rust 层（窗口管理、WS 客户端、系统托盘）
  - `ui/src/` — Vue3 前端源码
  - `gateway/tauri_platform.py` — 新增 TauriPlatform
  - `gateway/events.py` — 事件类型定义
  - `platforms/voice/events.py` — 语音平台事件广播接口
- **修改文件**：
  - `gateway/gateway.py` — 注册 TauriPlatform + 启动 Tauri 进程
  - `ultimate.py` — gateway 命令增加 `--no-gui` 选项
  - `config.yaml` — 新增 `gui:` 配置节
- **不涉及**：现有 VoicePlatform 的唤醒/STT/TTS 核心逻辑修改
```

## openspec/changes/jarvis-desktop-gui/design.md

- Source: openspec/changes/jarvis-desktop-gui/design.md
- Lines: 1-231
- SHA256: 7cfb4343fae523a10cdaa7a63301135238db1b0721135c9882905455495cf29f

[TRUNCATED]

```md
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
```

Full source: openspec/changes/jarvis-desktop-gui/design.md

## openspec/changes/jarvis-desktop-gui/tasks.md

- Source: openspec/changes/jarvis-desktop-gui/tasks.md
- Lines: 1-97
- SHA256: 0811fd65753044b3a080f6adb0c068554adc0b982313b4bf122fe292084a4f37

[TRUNCATED]

```md
## 1. 项目脚手架与依赖

- [ ] 1.1 创建 `ui/` 目录，初始化 Tauri + Vue3 + TypeScript 项目（Vite 构建）
- [ ] 1.2 添加 Tauri Rust 依赖：`tokio-tungstenite`（WS 客户端）、`serde_json`、`tray-icon`
- [ ] 1.3 添加 Vue3 前端依赖：无额外 UI 组件库（纯自绘 JARVIS 风格），仅保留 Vue3 + TypeScript + Vite
- [ ] 1.4 配置 Tauri `tauri.conf.json`：frameless 窗口、窗口初始隐藏、最小尺寸 800x600
- [ ] 1.5 配置 Vite 开发服务器端口和 Tauri 集成

## 2. Tauri Rust 窗口管理层

- [ ] 2.1 实现 WindowManager：show() / hide() 方法，Rust 层控制窗口生命周期
- [ ] 2.2 实现 fade-in 动画（show 时 300ms 透明度动画）
- [ ] 2.3 实现 fade-out 动画（hide 时 500ms 透明度动画）
- [ ] 2.4 实现系统托盘图标（创建、显示自定义图标）
- [ ] 2.5 实现托盘右键菜单：显示窗口、设置、退出
- [ ] 2.6 实现 frameless 窗口拖拽（定义拖拽区域，Vue3 配合 data-tauri-drag-region）
- [ ] 2.7 实现空闲倒计时自动隐藏（可配置倒计时时长，新事件打断重置）

## 3. Tauri Rust WebSocket 客户端

- [ ] 3.1 实现 WebSocketClient 结构体：connect() / send() / on_message() 接口
- [ ] 3.2 实现指数退避重连逻辑（500ms→10s 上限，最多 10 次）
- [ ] 3.3 实现 WS 消息 → Tauri event 转换（将 `{"event": "wake"}` 映射为 `tauri://wake` 事件）
- [ ] 3.4 实现 Vue3 → Tauri invoke 转发：用户输入/关闭事件 -> WS 发送到后端
- [ ] 3.5 实现握手协议：连接成功后发送 `{"event": "hello", "version": "1.0"}`

## 4. Python 后端：TauriPlatform（WebSocket Server）

- [ ] 4.1 新建 `gateway/tauri_platform.py`，实现 `TauriPlatform(BasePlatform)`
- [ ] 4.2 实现 aiohttp WebSocket Server 监听 `ws://127.0.0.1:<port>`
- [ ] 4.3 实现 `connections` 集合管理：add / remove / broadcast
- [ ] 4.4 实现 `broadcast(event: dict)` 方法：循环推送、自动清理断连
- [ ] 4.5 实现 `send_flow_text(text: str)` 方法：逐块推送流式文本事件

## 5. Python 后端：Gateway 集成

- [ ] 5.1 `gateway/gateway.py` 注册 TauriPlatform（注册到 Gateway，初始化 WS Server）
- [ ] 5.2 `ultimate.py` 的 `gateway_cmd()` 增加 Tauri 子进程启动逻辑
- [ ] 5.3 实现 Tauri 二进制文件自动发现（项目根目录、PATH、config.yaml 路径）
- [ ] 5.4 实现 `--no-gui` 命令行参数
- [ ] 5.5 实现 Gateway shutdown 钩子：kill Tauri 子进程、关闭 WS Server
- [ ] 5.6 在 `config.yaml` 中新增 `gui:` 配置节（ws_port、window 尺寸、auto_hide_delay）

## 6. Python 后端：VoicePlatform 事件广播集成

- [ ] 6.1 VoicePlatform 的唤醒回调中调用 `tauri_platform.broadcast({"event": "wake"})`
- [ ] 6.2 STT 完成后调用 `tauri_platform.broadcast({"event": "stt", "text": ...})`
- [ ] 6.3 AgentRunner 调用前/后广播 `thinking` 和 `text_chunk` 事件
- [ ] 6.4 TTS 开始/结束时广播 `tts_start` / `tts_end` 事件
- [ ] 6.5 交互完成时广播 `idle` 事件

## 7. Vue3 前端：核心 UI 框架

- [ ] 7.1 创建 `App.vue` 根组件：注册 Tauri event 监听器
- [ ] 7.2 创建 `useTauriEvents.ts` composable：封装事件监听（wake/stt/text_chunk/data/tts_start/tts_end/idle）
- [ ] 7.3 创建 `types/events.ts`：TypeScript 类型定义（所有 WS 事件类型）
- [ ] 7.4 App.vue 中实现全窗口 JARVIS 主题 CSS（暗色渐变背景、毛玻璃面板、发光边框）

## 8. Vue3 前端：动态波形组件

- [ ] 8.1 创建 `components/JarvisWaveform.vue`：Canvas 2D 渲染容器
- [ ] 8.2 实现圆形环形波纹绘制算法（多圈正弦波，透明度渐变）
- [ ] 8.3 实现波形模式：idle（呼吸光晕）、listening（振幅 pulsate）、thinking（缓慢脉冲）、speaking（活跃跳动）
- [ ] 8.4 通过 `requestAnimationFrame` 驱动 60fps 动画循环

## 9. Vue3 前端：对话与数据展示

- [ ] 9.1 创建 `components/ConversationView.vue`：对话消息列表容器
- [ ] 9.2 实现流式文本逐字追加效果（打字机效果，间隔可调）
- [ ] 9.3 实现消息气泡组件区分用户消息 / Agent 回复
- [ ] 9.4 创建 `components/DataTable.vue`：JARVIS 风格数据表格（深色主题、发光边界、交替行色）
- [ ] 9.5 实现 `text_chunk` 事件队列 - Agent 回复完成后尝试解析结构化数据
- [ ] 9.6 实现自动滚动到底部

## 10. Vue3 前端：输入与状态栏

- [ ] 10.1 创建 `components/StatusBar.vue`：显示当前状态（Listening / Thinking / Speaking）
- [ ] 10.2 创建 `components/InputBar.vue`：文本输入框组件（支持回车发送）
- [ ] 10.3 实现输入框提交逻辑：通过 Tauri invoke 发送到 Rust → WS 转发后端

```

Full source: openspec/changes/jarvis-desktop-gui/tasks.md

## openspec/changes/jarvis-desktop-gui/specs/desktop-protocol/spec.md

- Source: openspec/changes/jarvis-desktop-gui/specs/desktop-protocol/spec.md
- Lines: 1-123
- SHA256: 757b3ff71d8fa7bebf804fdbf4174b85a09827361810832ca9f7a64b473384d8

[TRUNCATED]

```md
# desktop-protocol

Python 后端与 Tauri 前端之间的 WebSocket 实时通信协议，定义事件类型、数据格式和流式传输规范。

## ADDED Requirements

### Requirement: WebSocket 连接生命周期

Tauri 应用启动后 SHALL 立即通过 Rust 层建立到 `ws://127.0.0.1:<port>` 的 WebSocket 连接。Python 端 SHALL 在 `TauriPlatform` 中运行 aiohttp WebSocket Server，监听指定端口（默认 18765）。

#### Scenario: Tauri 主动连接后端
- **WHEN** Tauri Rust 层初始化完成
- **THEN** 发起 WebSocket 连接到 `ws://127.0.0.1:18765`
- **AND** 连接成功后发送 `{"event": "hello", "version": "1.0"}` 握手消息
- **AND** 后端确认后开始转发事件

#### Scenario: 连接断开自动重连
- **WHEN** WebSocket 连接因后端重启/网络问题断开
- **THEN** Tauri Rust 层执行指数退避重连（500ms → 1s → 2s → 4s → 8s → 10s 上限，最多 10 次）
- **AND** 重连成功后重新订阅事件流

### Requirement: 后端 → 前端事件格式

所有后端到前端的事件 SHALL 使用 JSON 格式，包含 `event` 字段标识事件类型。

#### Scenario: 固定字段结构
- **WHEN** 后端推送事件
- **THEN** 消息体为 JSON 对象
- **AND** 包含 `event` 字段（字符串，事件类型标识）
- **AND** 可选字段按事件类型定义

### Requirement: 唤醒事件 (wake)

当 VoicePlatform 检测到唤醒词时，后端 SHALL 推送 `wake` 事件。

#### Scenario: 唤醒事件触发
- **WHEN** 唤醒词检测成功
- **THEN** 后端发送 `{"event": "wake"}`
- **AND** Tauri 收到后弹出窗口

### Requirement: 语音识别事件 (stt)

当 VoicePlatform 完成语音识别时，后端 SHALL 推送 `stt` 事件，携带识别文本。

#### Scenario: STT 结果推送
- **WHEN** 用户语音被转录为文本
- **THEN** 后端发送 `{"event": "stt", "text": "<识别结果>"}`
- **AND** 前端在波形旁边显示识别文本

### Requirement: 思考中事件 (thinking)

当后端正调用 LLM 处理用户输入时，SHALL 推送 `thinking` 事件。

#### Scenario: LLM 处理中
- **WHEN** AgentRunner 开始 LLM 调用
- **THEN** 后端发送 `{"event": "thinking"}`
- **AND** 前端显示「思考中⋯」状态指示
- **AND** 波形切换为缓慢脉冲模式

### Requirement: 流式文本事件 (text_chunk)

Agent 回复 SHALL 通过流式 `text_chunk` 事件逐段推送。后端 SHALL 在 LLM 每产生一段输出时就推送一次，支持高频小片段。

#### Scenario: 流式文本输出
- **WHEN** LLM 持续输出回复文本
- **THEN** 后端发送零次或多次 `{"event": "text_chunk", "text": "<文本片段>"}`
- **AND** 前端将文本片段追加到当前 AI 回复气泡

### Requirement: 结构化数据事件 (data)

当 Agent 的回复中包含结构化数据（如表格）、或执行工具返回数据时，后端 SHALL 推送 `data` 事件。

#### Scenario: 表格数据推送
- **WHEN** Agent 返回结构化表格数据
- **THEN** 后端发送：
```json
{
  "event": "data",
  "type": "table",
  "columns": ["ID", "Name", "Value"],
```

Full source: openspec/changes/jarvis-desktop-gui/specs/desktop-protocol/spec.md

## openspec/changes/jarvis-desktop-gui/specs/desktop-ui/spec.md

- Source: openspec/changes/jarvis-desktop-gui/specs/desktop-ui/spec.md
- Lines: 1-131
- SHA256: 160b6aff300d681270dea13d84f8a16577a8d3b10b405e616a98e591eb05a026

[TRUNCATED]

```md
# desktop-ui

Tauri + Vue3 桌面 GUI 应用，提供 JARVIS 风格的全息交互界面。

## ADDED Requirements

### Requirement: Gateway 启动时自动拉起 Tauri 进程

当用户运行 `ultimate.py gateway` 时，Gateway SHALL 自动通过 `subprocess.Popen` 启动 Tauri 二进制文件。Tauri 应用启动后 SHALL 只显示系统托盘图标，窗口保持隐藏状态。

#### Scenario: Gateway 正常启动 Tauri 应用
- **WHEN** 用户执行 `python ultimate.py gateway`
- **THEN** Gateway 启动 Tauri 二进制进程
- **AND** Tauri 应用出现在系统托盘区域
- **AND** GUI 窗口处于隐藏状态

#### Scenario: --no-gui 参数跳过 Tauri 启动
- **WHEN** 用户执行 `python ultimate.py gateway --no-gui`
- **THEN** Gateway 正常启动
- **AND** 不启动 Tauri 进程

#### Scenario: Tauri 二进制不存在时优雅降级
- **WHEN** Gateway 尝试启动 Tauri 但二进制未找到
- **THEN** Gateway 记录警告日志
- **AND** 继续以纯 Gateway 模式运行
- **AND** 不阻塞其他平台的正常运行

### Requirement: 窗口唤醒弹出与自动隐藏

Tauri 窗口 SHALL 在收到后端 `wake` 事件时从隐藏状态弹出，并播放 fade-in 动画（~300ms）。在收到 `idle` 事件后等待 N 秒无交互，自动执行 fade-out 动画（~500ms）后隐藏。

#### Scenario: 唤醒词触发窗口弹出
- **WHEN** 后端 VoicePlatform 检测到唤醒词
- **AND** Tauri 收到 WS `{"event": "wake"}` 
- **THEN** Tauri Rust 层调用 `window.show()`
- **AND** 窗口以 fade-in 动画弹出（300ms）

#### Scenario: 交互结束自动隐藏
- **WHEN** 后端发送 `{"event": "idle"}`
- **THEN** Tauri 启动 N 秒倒计时（默认 10s，可配置）
- **AND** 倒计时内无新事件则执行 fade-out 动画（500ms）
- **AND** 动画完成后调用 `window.hide()`

#### Scenario: 新事件中断隐藏倒计时
- **WHEN** 隐藏倒计时进行中
- **AND** 后端发送新事件（如 wake/stt/thinking）
- **THEN** 倒计时取消
- **AND** 窗口保持显示状态

### Requirement: 系统托盘图标

Tauri 应用 SHALL 在系统通知区域显示图标，支持右键菜单。

#### Scenario: 托盘中正常显示
- **WHEN** Tauri 应用启动
- **THEN** 系统托盘区域显示自定义图标（JARVIS 风格）
- **AND** 图标单双击无默认行为（窗口由事件控制）

#### Scenario: 托盘右键菜单
- **WHEN** 用户在托盘图标上右键
- **THEN** 弹出菜单包含：
  - 「显示/隐藏窗口」
  - 「设置」
  - 「退出」

### Requirement: JARVIS 全息视觉主题

GUI 窗口 SHALL 采用 JARVIS 风格的全息视觉设计，包含深色背景、蓝色发光 accent、半透明毛玻璃面板、动态边框发光效果。

#### Scenario: 默认主题应用
- **WHEN** Tauri 窗口首次显示
- **THEN** 背景为深空蓝黑色（#0a0a1a）
- **AND** 面板为半透明毛玻璃效果（backdrop-filter: blur）
- **AND** 边框带蓝色发光效果（box-shadow + border）
- **AND** accent 色为 #00d4ff

### Requirement: 动态音频波形

GUI 窗口中央 SHALL 显示环形动态波形。波形风格为 JARVIS 环形脉冲，使用 Canvas 2D 渲染，通过 requestAnimationFrame 驱动 60fps 动画。

```

Full source: openspec/changes/jarvis-desktop-gui/specs/desktop-ui/spec.md

## openspec/changes/jarvis-desktop-gui/specs/voice-core/spec.md

- Source: openspec/changes/jarvis-desktop-gui/specs/voice-core/spec.md
- Lines: 1-72
- SHA256: 8b6c69f84716f79ed75ee6bb18a8c99b06b7c2a136b3a9c823e88cf0e2fb3a7f

```md
# voice-core

Voice platform core module — 增加 GUI 事件广播接口。

## ADDED Requirements

### Requirement: TauriPlatform 事件广播

VoicePlatform SHALL 在关键生命周期点调用 `TauriPlatform.broadcast()` 推送事件。TauriPlatform SHALL 提供 `broadcast()` 方法，向所有连接中的 Tauri 客户端发送 JSON 事件。

#### Scenario: VoicePlatform 使用 TauriPlatform 广播
- **GIVEN** Gateway 已注册 VoicePlatform 和 TauriPlatform
- **WHEN** VoicePlatform 检测到唤醒词
- **THEN** 调用 `tauri_platform.broadcast({"event": "wake"})`
- **AND** 所有连接的 Tauri 客户端收到该事件

#### Scenario: STT 完成后推送文本
- **GIVEN** VoicePlatform 已唤醒，进入命令模式
- **WHEN** STT 完成用户语音转录
- **THEN** 调用 `tauri_platform.broadcast({"event": "stt", "text": "<转录结果>"})`

#### Scenario: LLM 回复逐段推送
- **GIVEN** AgentRunner 正在生成回复
- **WHEN** LLM 输出新文本块
- **THEN** 调用 `tauri_platform.broadcast({"event": "text_chunk", "text": "<文本块>"})`
- **AND** 可在主循环中多次调用

#### Scenario: 结构化数据推送
- **GIVEN** Agent 的工具调用返回结构化数据
- **WHEN** 数据经过格式化适合表格展示
- **THEN** 调用 `tauri_platform.broadcast({"event": "data", "type": "table", ...})`

### Requirement: TTS 生命周期事件广播

VoicePlatform SHALL 在 TTS 合成开始和结束时广播状态事件，使前端能同步切换波形模式。

#### Scenario: TTS 开始广播
- **WHEN** TTS 合成完成并开始播放
- **THEN** 调用 `tauri_platform.broadcast({"event": "tts_start"})`

#### Scenario: TTS 结束广播
- **WHEN** TTS 播放结束
- **THEN** 调用 `tauri_platform.broadcast({"event": "tts_end"})`

### Requirement: 空闲事件广播

VoicePlatform SHALL 在完成完整交互链路（唤醒→STT→LLM→TTS）后广播 `idle` 事件。

#### Scenario: 交互完成广播
- **WHEN** Agent 回复完成
- **AND** TTS 播放结束
- **AND** 返回监听状态
- **THEN** 调用 `tauri_platform.broadcast({"event": "idle"})`

### Requirement: TauriPlatform 连接管理

TauriPlatform SHALL 管理 WebSocket 连接集合，提供广播和连接状态追踪能力。

#### Scenario: 新增连接
- **WHEN** 新的 Tauri 客户端 WebSocket 连接建立
- **THEN** 该连接被加入 `connections` 集合
- **AND** 日志记录新连接信息

#### Scenario: 移除断连
- **WHEN** 客户端 WebSocket 连接断开
- **THEN** 该连接被从 `connections` 集合中移除
- **AND** 日志记录断连信息

#### Scenario: 广播自动清理死连接
- **WHEN** `broadcast()` 向某连接发消息失败
- **THEN** 该连接被自动从 `connections` 集合移除
- **AND** 广播继续发送给其他连接
```

