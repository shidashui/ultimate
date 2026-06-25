# Comet Design Handoff

- Change: provider-streaming-refactor
- Phase: design
- Mode: compact
- Context hash: 18a123730ffb6077c968e263f10dec121c313e478d49b7e028869e5de20af600

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/provider-streaming-refactor/proposal.md

- Source: openspec/changes/provider-streaming-refactor/proposal.md
- Lines: 1-29
- SHA256: 1ff69ebb9b4c87710c5f6bb880ed8455d1b95359949b333530af61d7dac49a37

```md
## Why

AgentRunner 当前的 LLM 调用链路是 one-shot 全量返回：`run_turn() → ContextGuard → provider.chat()`。JARVIS 桌面 GUI 需要 Agent 回复的流式文本推送（`text_chunk` 事件），而底层 Anthropic SDK 原生支持 streaming，能力已有但被完全封装隐藏。此变更为后续 GUI 项目提供前置能力。

## What Changes

- `BaseProvider` 新增 `chat_stream(messages, system, tools, on_chunk) → Response` 抽象方法
- `AnthropicProvider` 实现 `chat_stream()`，基于 Anthropic SDK `stream=True` + `text_stream` 异步迭代
- `AgentRunner.run_turn()` 增加可选 `on_text_chunk: Callable[[str], None] | None` 参数
- 有回调时走精简 streaming 循环（不加 ContextGuard 重试包裹），无回调时走原有 one-shot 路径，全程零变更

## Capabilities

### New Capabilities
- `provider-streaming`: LLM provider 流式响应接口，支持逐 chunk 回调

### Modified Capabilities
- `base-provider`: BaseProvider 接口新增 `chat_stream()` 抽象方法；AnthropicProvider 新增 streaming 实现；AgentRunner 新增可选流式回调参数

## Impact

- **修改文件**（~4 个，共约 60 行新增/修改）：
  - `agentd/providers/base.py` — 新增 `chat_stream()` 抽象方法签名
  - `agentd/providers/anthropic.py` — 实现 `chat_stream()`（~25 行）
  - `agentd/agent/runner.py` — `run_turn()` 增加 `on_text_chunk` 参数和 streaming 分支（~20 行）
- **不修改**：
  - `agentd/context/context.py` — ContextGuard 保持不变
  - `agentd/providers/router.py` — Router 保持不变
  - 所有现有调用者 — `on_text_chunk` 默认 None，行为等价
```

## openspec/changes/provider-streaming-refactor/design.md

- Source: openspec/changes/provider-streaming-refactor/design.md
- Lines: 1-196
- SHA256: f309d3cf91e13130e525d6f8e91bac3675553a98523e15649563dcd930a410f2

[TRUNCATED]

```md
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

Full source: openspec/changes/provider-streaming-refactor/design.md

## openspec/changes/provider-streaming-refactor/tasks.md

- Source: openspec/changes/provider-streaming-refactor/tasks.md
- Lines: 1-33
- SHA256: 67070eca7a92e67fd3b62fb406b097dbc4c9e1a31b3cf4de4744799abfed084b

```md
## 1. BaseProvider 抽象方法

- [ ] 1.1 在 `agentd/providers/base.py` 的 `BaseProvider` 中新增 `chat_stream()` 抽象方法签名

## 2. AnthropicProvider 流式实现

- [ ] 2.1 在 `agentd/providers/anthropic.py` 的 `AnthropicProvider` 中实现 `chat_stream()` 方法
- [ ] 2.2 使用 `AsyncAnthropic.messages.stream()` SDK API + `text_stream` 异步迭代
- [ ] 2.3 实现 `stream.get_final_message()` 归一化为 `Response`
- [ ] 2.4 抽取 ContentBlock 归一化逻辑为私有方法（chat 和 chat_stream 共用）

## 3. ContextGuard 流式保护

- [ ] 3.1 `agentd/context/context.py` 中 `ContextGuard` 新增 `async_guard_stream_call()` 方法
- [ ] 3.2 实现预飞压缩（`preflight()` 在 `chat_stream()` 前执行）
- [ ] 3.3 实现上下文溢出三级处理（截断 → 压缩 → 抛异常）
- [ ] 3.4 实现 AUTH_FAILURE / MODEL_UNAVAILABLE 的 provider 切换重试
- [ ] 3.5 RATE_LIMIT / SERVER_ERROR / TIMEOUT 直接抛出，不重试

## 4. AgentRunner 流式分支

- [ ] 4.1 `run_turn()` 增加 `on_text_chunk` 可选参数
- [ ] 4.2 当 `on_text_chunk` 非 None 时走 `guard.async_guard_stream_call()` 路径
- [ ] 4.3 Streaming 路径中 tool_use 循环复用已有 `process_tool_call()` 逻辑
- [ ] 4.4 Streaming 路径异常处理：调用 `_rollback(messages)` 后返回空字符串
- [ ] 4.5 现有 one-shot 路径不修改（无回调时行为完全不变）

## 5. 验证

- [ ] 5.1 手动测试：CLI 模式 `python ultimate.py chat` 确认行为不变
- [ ] 5.2 手动测试：传入回调 `on_text_chunk=lambda t: print(t)` 验证流式输出
- [ ] 5.3 手动测试：模拟 stream 中断，验证 rollback + 空返回
- [ ] 5.4 运行现有测试 `python test.py` 确认无回归
```

## openspec/changes/provider-streaming-refactor/specs/base-provider/spec.md

- Source: openspec/changes/provider-streaming-refactor/specs/base-provider/spec.md
- Lines: 1-51
- SHA256: 67ec3d5934dc4f3e9515f390aaeb7cc89c9c65a9305475f4bcb19172e90ce6a0

```md
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
```

## openspec/changes/provider-streaming-refactor/specs/provider-streaming/spec.md

- Source: openspec/changes/provider-streaming-refactor/specs/provider-streaming/spec.md
- Lines: 1-87
- SHA256: bb157d6c070913ef97f792345fed1416aea8a7a329194b049431dfca17d535c2

[TRUNCATED]

```md
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
```

Full source: openspec/changes/provider-streaming-refactor/specs/provider-streaming/spec.md

