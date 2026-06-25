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
  "rows": [
    [1, "Item A", 100],
    [2, "Item B", 200]
  ]
}
```
- **AND** 前端渲染为 JARVIS 风格表格

### Requirement: TTS 状态事件 (tts_start / tts_end)

在 TTS 音频开始和结束时，后端 SHALL 推送对应事件。

#### Scenario: TTS 生命周期
- **WHEN** TTS 合成开始播放
- **THEN** 后端发送 `{"event": "tts_start"}`
- **AND** 前端波形切换为活跃跳动模式
- **WHEN** TTS 播放完成
- **THEN** 后端发送 `{"event": "tts_end"}`

### Requirement: 空闲事件 (idle)

当一次完整的交互（唤醒→STT→LLM→TTS）完成，系统回到监听状态时，后端 SHALL 推送 `idle` 事件。

#### Scenario: 交互结束
- **WHEN** Agent 回复完成 + TTS 播放结束
- **AND** 无新的语音/文本输入
- **THEN** 后端发送 `{"event": "idle"}`
- **AND** 启动窗口自动隐藏倒计时

### Requirement: 前端 → 后端事件

前端 SHALL 支持向后端发送用户输入和窗口状态事件。

#### Scenario: 键盘输入
- **WHEN** 用户在输入框键入文本并回车
- **THEN** 发送 `{"event": "input", "text": "<用户文本>"}`
- **AND** 后端将该文本提交到 AgentRunner 处理

#### Scenario: 用户主动关闭
- **WHEN** 用户点击关闭按钮
- **THEN** 前端发送 `{"event": "close"}`
- **AND** 后端记录状态
- **AND** Tauri 执行窗口隐藏
