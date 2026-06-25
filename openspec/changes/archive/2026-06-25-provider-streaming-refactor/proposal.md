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
