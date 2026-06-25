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
