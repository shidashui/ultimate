## 1. BaseProvider 抽象方法

- [x] 1.1 在 `agentd/providers/base.py` 的 `BaseProvider` 中新增 `chat_stream()` 抽象方法签名

## 2. AnthropicProvider 流式实现

- [x] 2.1 在 `agentd/providers/anthropic.py` 的 `AnthropicProvider` 中实现 `chat_stream()` 方法
- [x] 2.2 使用 `AsyncAnthropic.messages.stream()` SDK API + `text_stream` 异步迭代
- [x] 2.3 实现 `stream.get_final_message()` 归一化为 `Response`
- [x] 2.4 抽取 ContentBlock 归一化逻辑为私有方法（chat 和 chat_stream 共用）

## 3. ContextGuard 流式保护

- [x] 3.1 `agentd/context/context.py` 中 `ContextGuard` 新增 `async_guard_stream_call()` 方法
- [x] 3.2 实现预飞压缩（`preflight()` 在 `chat_stream()` 前执行）
- [x] 3.3 实现上下文溢出三级处理（截断 → 压缩 → 抛异常）
- [x] 3.4 实现 AUTH_FAILURE / MODEL_UNAVAILABLE 的 provider 切换重试
- [x] 3.5 RATE_LIMIT / SERVER_ERROR / TIMEOUT 直接抛出，不重试

## 4. AgentRunner 流式分支

- [x] 4.1 `run_turn()` 增加 `on_text_chunk` 可选参数
- [x] 4.2 当 `on_text_chunk` 非 None 时走 `guard.async_guard_stream_call()` 路径
- [x] 4.3 Streaming 路径中 tool_use 循环复用已有 `process_tool_call()` 逻辑
- [x] 4.4 Streaming 路径异常处理：调用 `_rollback(messages)` 后返回空字符串
- [x] 4.5 现有 one-shot 路径不修改（无回调时行为完全不变）

## 5. 验证

- [x] 5.1 手动测试：CLI 模式 `python ultimate.py chat` 确认行为不变
- [x] 5.2 手动测试：传入回调 `on_text_chunk=lambda t: print(t)` 验证流式输出
- [x] 5.3 手动测试：模拟 stream 中断，验证 rollback + 空返回
- [x] 5.4 运行现有测试 `python test.py` 确认无回归
