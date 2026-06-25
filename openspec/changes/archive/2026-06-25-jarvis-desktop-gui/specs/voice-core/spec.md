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
