---
comet_change: provider-streaming-refactor
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-25-provider-streaming-refactor
status: final
---

# Provider Streaming Refactor — Technical Design

## Context

Anthropic SDK 原生支持 streaming (`stream=True`)，但现有代码用 `client.messages.create()` 一次性返回完整 Response。JARVIS GUI 需要流式 `text_chunk` 推送。此设计为 BaseProvider / ContextGuard / AgentRunner 三层增加 streaming 通道，与现有 one-shot 路径并存。

## Architecture

```
AgentRunner.run_turn(on_text_chunk?)
        │
        ├── None → guard.async_guard_api_call() → provider.chat()
        │           (原有路径, 零变更)
        │
        └── callback → guard.async_guard_stream_call() → provider.chat_stream()
                        (新增路径)
```

### Layer 1: BaseProvider

新增 `chat_stream()` 抽象方法，回调驱动：每收到 text chunk 调用 `on_text_chunk(text)`，流结束后返回完整 `Response`。

### Layer 2: AnthropicProvider

使用 `AsyncAnthropic.messages.stream()` SDK API，通过 `stream.text_stream` 异步迭代获取文本块。ContentBlock 归一化逻辑抽取为共用私有方法。

### Layer 3: ContextGuard

新增 `async_guard_stream_call()`，与 `async_guard_api_call()` 同级保护：

| 保护 | one-shot | streaming | 原因 |
|------|----------|-----------|------|
| Preflight | ✅ | ✅ | 调用前执行，安全 |
| Overflow | ✅ | ✅ | stream 建立前检测 |
| Provider 切换 | ✅ | ✅ | 连接级，安全 |
| RATE_LIMIT 重试 | ✅ | ❌ | chunks 可能已发出 |
| SERVER_ERROR 重试 | ✅ | ❌ | 同上 |
| TIMEOUT 重试 | ✅ | ❌ | 同上 |

### Layer 4: AgentRunner

`run_turn()` 新增可选 `on_text_chunk` 参数。非 None 时走 guard stream 路径，tool_use 循环复用已有逻辑。

### Error Recovery

Stream 中断时：AgentRunner rollback + return "" → VoicePlatform error 事件 → GUI 标记 interrupted → 用户重新唤醒覆盖。

## Files Changed

| File | Change |
|------|--------|
| `agentd/providers/base.py` | `chat_stream()` abstract method |
| `agentd/providers/anthropic.py` | `chat_stream()` impl + shared normalization |
| `agentd/context/context.py` | `ContextGuard.async_guard_stream_call()` |
| `agentd/agent/runner.py` | `run_turn()` optional `on_text_chunk` param |

## Testing

1. Regression: CLI `ultimate.py chat` unchanged behavior
2. Functional: `on_text_chunk` callback receives streamed text
3. Exception: simulated stream break → rollback + empty return
4. Existing: `python test.py` all pass
