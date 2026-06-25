# provider-streaming

LLM provider 流式响应接口，支持逐 chunk 回调和错误处理。

## ADDED Requirements

### Requirement: BaseProvider 提供 chat_stream 抽象方法

`BaseProvider` SHALL 提供 `chat_stream()` 抽象方法，支持流式文本回调。调用方传入 `on_text_chunk` 回调函数，每收到一个文本块时被调用。

#### Scenario: 流式文本逐块回调
- **WHEN** 调用方以 `on_text_chunk=print` 调用 `chat_stream()`
- **THEN** LLM 流式输出过程中 `print(text)` 被多次调用
- **AND** 每次调用参数为文本片段字符串
- **AND** 返回值为完整的 `Response` 对象

#### Scenario: 无回调时行为等同 chat
- **WHEN** 调用方以 `on_text_chunk=None` 调用 `chat_stream()`
- **THEN** 返回完整 `Response` 对象
- **AND** 不触发任何回调

### Requirement: AnthropicProvider 实现 chat_stream

`AnthropicProvider` SHALL 使用 Anthropic SDK 的 `messages.stream()` API 实现 `chat_stream()`。

#### Scenario: SDK streaming 集成
- **WHEN** `AnthropicProvider.chat_stream()` 被调用
- **THEN** 底层调用 `AsyncAnthropic.messages.stream(stream=True, ...)`
- **AND** 通过 `stream.text_stream` 异步迭代器获取文本块
- **AND** 每个非空文本块调用 `on_text_chunk(text)`

#### Scenario: 流式调用后返回完整 Response
- **WHEN** streaming 完成（`text_stream` 迭代结束）
- **THEN** 调用 `stream.get_final_message()` 获取最终消息
- **AND** 返回归一化的 `Response(content=..., stop_reason=...)`

### Requirement: ContextGuard 提供 async_guard_stream_call

`ContextGuard` SHALL 提供 `async_guard_stream_call()` 方法，对 streaming 调用提供与 one-shot 路径对等的保护。

#### Scenario: 预飞压缩在 streaming 前执行
- **WHEN** 调用 `async_guard_stream_call()` 且上下文超过阈值
- **THEN** 在 `chat_stream()` 调用前执行 `preflight()` 压缩
- **AND** 压缩时零 chunk 已发出

#### Scenario: 上下文溢出安全处理
- **WHEN** `chat_stream()` 抛出 CONTEXT_OVERFLOW 错误
- **THEN** 先截断大工具结果后重试（一次）
- **AND** 仍溢出则压缩历史后重试（一次）
- **AND** 仍溢出则抛出异常

#### Scenario: 认证失败切换 provider
- **WHEN** `chat_stream()` 抛出 AUTH_FAILURE 或 MODEL_UNAVAILABLE 错误
- **AND** 有备用 provider 可用
- **THEN** 切换到备用 provider 后重试

#### Scenario: 运行时错误不重试
- **WHEN** `chat_stream()` 抛出 RATE_LIMIT 或 SERVER_ERROR 或 TIMEOUT 错误
- **THEN** 直接抛出异常，不重试

### Requirement: AgentRunner 支持流式回调

`AgentRunner.run_turn()` SHALL 接受可选参数 `on_text_chunk: Callable[[str], None] | None`。

#### Scenario: 传入回调时走 streaming guard 路径
- **WHEN** `run_turn()` 传入非 None 的 `on_text_chunk` 回调
- **THEN** AgentRunner 的核心 LLM 调用使用 `guard.async_guard_stream_call()`
- **AND** tool_use 循环复用与 one-shot 路径相同的逻辑

#### Scenario: 未传入回调时走 one-shot 路径
- **WHEN** `run_turn()` 以默认 `on_text_chunk=None` 调用
- **THEN** 行为与重构前完全一致
- **AND** 走 `guard.async_guard_api_call() → provider.chat()` 路径

### Requirement: Stream 中断时的错误处理

当 streaming 中途连接断开，AgentRunner SHALL rollback 当前用户消息并返回空字符串。

#### Scenario: Stream 中断后回滚
- **WHEN** `chat_stream()` 在 streaming 中抛出异常（非 CONTEXT_OVERFLOW、非 AUTH_FAILURE、非 MODEL_UNAVAILABLE）
- **THEN** AgentRunner 调用 `_rollback(messages)`
- **AND** 返回空字符串 `""`

#### Scenario: 调用方通过空返回检测中断
- **WHEN** 调用方（VoicePlatform）收到空字符串返回
- **THEN** 调用方应向 GUI 发送 error 事件表示 stream 中断
- **AND** GUI 将当前"进行中"回复标记为 interrupted
