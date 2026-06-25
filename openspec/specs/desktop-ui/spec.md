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

#### Scenario: 不同状态切换波形模式
- **WHEN** 后端状态变化并推送事件
- **THEN** 波形模式随事件切换：
  - `idle` → 微弱呼吸光晕
  - `wake` / `stt` → 环形波纹跟随振幅 pulsate
  - `thinking` → 缓慢脉冲
  - `tts_start` → 活跃跳动（跟随 TTS 音频输出）

### Requirement: 流式对话渲染

GUI 对话区域 SHALL 支持流式文本追加渲染，Agent 回复以打字机效果逐字显示。

#### Scenario: 流式文本显示
- **WHEN** 后端推送 `{"event": "text_chunk", "text": "..."}` 事件序列
- **THEN** 前端将文本追加到当前 Agent 回复气泡
- **AND** 回复气泡以打字机效果逐步显示
- **AND** 对话区域自动滚动到最新内容

### Requirement: 结构化数据表格渲染

GUI 对话区域 SHALL 支持嵌入结构化数据表格。Agent 在回复中包含特定格式时，前端渲染为可读的数据表格。

#### Scenario: 数据表格渲染
- **WHEN** 后端推送 `{"event": "data", "type": "table", "data": [...]}`
- **THEN** 前端在对话流中渲染为 HTML 表格
- **AND** 表格包含表头、行数据、交替行背景色
- **AND** 表格样式匹配全息主题

### Requirement: 键盘输入支持

GUI SHALL 支持用户通过键盘输入文本与 Agent 交互。

#### Scenario: 键盘输入文本
- **WHEN** 用户在输入框中输入文字并回车
- **THEN** 该文本被发送到后端处理（通过 WS → AgentRunner）
- **AND** 输入框内容清空
- **AND** 前端显示用户消息气泡

### Requirement: 窗口 frameless 样式

Tauri 窗口 SHALL 采用 frameless（无边框）样式，由 Rust 层实现自绘标题栏和拖拽区域。

#### Scenario: 窗口拖拽
- **WHEN** 用户在窗口中定义的拖拽区域按下鼠标并拖动
- **THEN** 窗口跟随鼠标移动
- **AND** 拖拽过程中窗口保持半透明状态

#### Scenario: 窗口关闭按钮
- **WHEN** 用户点击关闭按钮
- **THEN** 窗口执行 fade-out 动画并隐藏（而非关闭应用）
- **AND** 应用继续在系统托盘运行
