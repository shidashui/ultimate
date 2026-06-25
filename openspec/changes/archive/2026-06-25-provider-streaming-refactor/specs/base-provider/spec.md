# base-provider

BaseProvider 接口新增流式调用和 ContextGuard 流式保护能力。

## ADDED Requirements

### Requirement: BaseProvider chat_stream 接口

`BaseProvider` SHALL 提供 `chat_stream()` 抽象方法：

```python
@abstractmethod
async def chat_stream(
    self,
    messages: list[dict],
    system: str | list,
    tools: list[dict] | None = None,
    on_text_chunk: Callable[[str], None] | None = None,
    **kwargs,
) -> Response:
    ...
```

#### Scenario: chat_stream 签名一致性
- **WHEN** 子类实现 `chat_stream()`
- **THEN** 方法签名与抽象基类一致
- **AND** 返回值为 `Response` 类型

### Requirement: ContextGuard 提供 async_guard_stream_call

`ContextGuard` SHALL 提供 `async_guard_stream_call()` 方法，对 streaming 调用提供预飞压缩、上下文溢出处理和 provider 级别切换保护。

#### Scenario: 预飞压缩在 streaming 前执行
- **WHEN** 调用 `async_guard_stream_call()`
- **THEN** 先调用 `preflight()` 检查并压缩消息
- **AND** 压缩完成后才调用 `provider.chat_stream()`

#### Scenario: 上下文溢出三级处理
- **WHEN** `chat_stream()` 抛出 CONTEXT_OVERFLOW
- **THEN** 第一级：截断大工具结果后重试
- **AND** 第二级：压缩对话历史后重试
- **AND** 第三级：抛出异常

#### Scenario: Provider 切换
- **WHEN** `chat_stream()` 抛出 AUTH_FAILURE 或 MODEL_UNAVAILABLE
- **AND** ProviderRouter 有可用备用 provider
- **THEN** 切换到备用 provider 后重试

#### Scenario: 运行时错误不重试
- **WHEN** `chat_stream()` 抛出 RATE_LIMIT、SERVER_ERROR 或 TIMEOUT
- **THEN** 不重试，直接抛出异常
