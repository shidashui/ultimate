## Context

Anthropic SDK 的 `AsyncAnthropic.messages.create()` 支持 `stream=True`，返回流式迭代器，提供 `text_stream` 异步生成器逐块产出文本。当前代码使用无 `stream` 参数（默认 `False`）的一次性调用，返回完整 Response。

调用链：
```
AgentRunner.run_turn()
  → ContextGuard.async_guard_api_call()    # 重试+错误处理
      → provider.chat()                     # one-shot
          → SDK client.messages.create()
```

## Goals / Non-Goals

**Goals:**
- BaseProvider 新增 `chat_stream()` 方法，语义为"流式产生文本 chunks + 最后返回完整 Response"
- AnthropicProvider 用 SDK streaming API 实现
- ContextGuard 新增 `async_guard_stream_call()`，提供与 one-shot 路径对等的保护（预飞压缩 + 溢出处理 + provider 切换）
- AgentRunner.run_turn() 在传入回调时走 guard stream 路径，未传入时走原 one-shot 路径

**Non-Goals:**
- 不修改 tool_handlers
- 不涉及 memory、session 等其他模块

## Decisions

### D1: `chat_stream()` 签名设计

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
    """流式聊天 — 每收到 text chunk 调用 on_text_chunk，最终返回完整 Response。"""
```

### D2: AnthropicProvider 实现方式

```python
async def chat_stream(self, messages, system, tools=None,
                     on_text_chunk=None, **kwargs) -> Response:
    kwargs.setdefault("max_tokens", 8096)
    kwargs["model"] = self._model
    kwargs["system"] = system
    kwargs["messages"] = messages
    if tools:
        kwargs["tools"] = tools

    async with self._client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            if on_text_chunk and text:
                on_text_chunk(text)

    final = stream.get_final_message()
    # 归一化 — 复用与 chat() 相同的 ContentBlock 转换逻辑
    ...
    return Response(content=..., stop_reason=...)
```

### D3: ContextGuard 新增 `async_guard_stream_call()`

与 `async_guard_api_call()` 同级保护，两条路径共享 guard 逻辑：

```
                      ContextGuard
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
   async_guard_api_call()      async_guard_stream_call()
   (one-shot, 已有)             (streaming, 新增)
           │                           │
      full retry                  selective retry
      (RATE_LIMIT/                (仅 overflow +
       SERVER_ERROR/               auth fail +
       TIMEOUT 也重试)             model unavailable)
```

API 语义区分：

| 错误类型 | stream 建立前 | stream 建立后 |
|----------|-------------|-------------|
| CONTEXT_OVERFLOW | ✅ 安全 — 零 chunk 发出，截断/压缩后重试 | 不可能 — overflow 在 stream 建立阶段检测，不会中途出现 |
| AUTH_FAILURE | ✅ 安全 — 切换 provider 后重试 | 同上 |
| MODEL_UNAVAILABLE | ✅ 安全 — 切换 provider 后重试 | 同上 |
| RATE_LIMIT | ❌ 不重试 — 可能已有 chunk 发出 | ❌ |
| SERVER_ERROR | ❌ 不重试 — 同上 | ❌ |
| TIMEOUT | ❌ 不重试 — 同上 | ❌ |

实现：

```python
async def async_guard_stream_call(
    self, system, messages, tools=None, on_chunk=None
) -> Response:
    current_messages = messages
    timeout_s = 30
    overflow_attempt = 0

    for attempt in range(3):  # 安全上限
        provider = self._get_provider()
        try:
            # 预飞压缩 — 两条路径共享
            current_messages = await self.preflight(system, current_messages)

            return await provider.chat_stream(
                messages=current_messages,
                system=system,
                tools=tools,
                on_text_chunk=on_chunk,
                timeout=timeout_s,
            )
        except Exception as exc:
            err = classify(exc)

            # ✅ 安全保留 — overflow 在 stream 建立前检测
            if err.error_type == ErrorType.CONTEXT_OVERFLOW:
                if overflow_attempt == 0:
                    current_messages = self._truncate_large_tool_results(current_messages)
                    overflow_attempt += 1
                elif overflow_attempt == 1:
                    current_messages = await self.compact_history(current_messages)
                    overflow_attempt += 1
                else:
                    raise

            # ✅ 安全重试 — provider 级别切换
            elif err.error_type in (ErrorType.AUTH_FAILURE,
                                     ErrorType.MODEL_UNAVAILABLE):
                if self._router and self._router.switch():
                    continue
                raise

            # ❌ 不重试 — chunks 可能已发出
            else:
                raise

    raise RuntimeError("async_guard_stream_call: exhausted all retries")
```

### D4: AgentRunner 的 streaming 分支

```python
async def run_turn(
    self, user_input, messages, store, channel="terminal",
    on_text_chunk: Callable[[str], None] | None = None,
) -> str:
```

当 `on_text_chunk` 不为 None 时走 `async_guard_stream_call()`，否则走原有 `async_guard_api_call()`。两条路径完全对等：

```
on_text_chunk is None?      on_text_chunk is not None?
        │                              │
        ▼                              ▼
guard.async_guard_api_call()  guard.async_guard_stream_call()
        │                              │
        └──────────┬───────────────────┘
                   ▼
            tool_use 循环（公用逻辑）
```

### D5: Stream 中断后的错误处理

当 streaming 中途连接断开，AgentRunner 做 rollback + 返回空字符串。VoicePlatform 检测到空返回后向 GUI 发送 error 事件。GUI 将当前"进行中"的回复气泡标记为 interrupted，保留已显示的部分文本。

```
Stream 正常:           Stream 中断:
chunk A → GUI          chunk A → GUI
chunk B → GUI          chunk B → GUI
chunk C → GUI          chunk C → GUI
done → GUI             ── 中断 ──
                       AgentRunner: rollback + return ""
                       VoicePlatform → GUI: {"event": "error",
                                              "reason": "stream_interrupted"}
                       GUI: 标记气泡 "⚡连接中断"，保留 A/B/C
```

GUI 收到下一个 `text_chunk` 事件时清空旧气泡 + 重新渲染新回复（新回复覆盖）。

### D6: 不影响现有 one-shot 路径

`on_text_chunk` 默认为 None，所有现有调用者（CLI、Gateway）不改一行代码，行为完全等价。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| Streaming 中途 RATE_LIMIT/SERVER_ERROR/TIMEOUT 不重试 | GUI 标记 partial text + error 状态，用户重新唤醒重试；VoicePlatform 可做自动重试（新回复覆盖） |
| `stream.get_final_message()` 在某些 SDK 版本行为差异 | Anthropic SDK 文档 + 实测确认 stream 结束后此方法同步可用 |
| Streaming + tool_use 循环：每次工具调用后又走 streaming | 工具调用本身是瓶颈，streaming 额外开销可忽略 |
| 长对话可能触发 preflight 压缩 | `async_guard_stream_call()` 保留预飞压缩，调用前执行，压缩时零 chunk 发出 |
