# Proposal: 错误分类 + 差异化重试

## 问题背景

当前代码库中 API 调用层的异常处理全部使用 `except Exception` 兜底：

- **`ContextGuard.async_guard_api_call`**：用字符串匹配 `"context" in str(exc)` 判断上下文溢出，不同 provider 错误格式不同，极易误判
- **`AgentRunner.run_turn`**：捕获所有异常后 `log + rollback + return ""`，限流、认证失败、超时被一视同仁地吞掉
- **`AnthropicProvider.chat`**：无任何异常处理，SDK 异常原样上抛
- **`ContextGuard.compact_history`**：摘要 LLM 调用失败直接丢旧消息，无重试

Anthropic SDK 本身有完整的异常层次（`APIStatusError` → `RateLimitError` / `AuthenticationError` / `InternalServerError` / `APITimeoutError` 等），但完全未被利用。

## 目标

建立**类型化错误分类 + 策略分发**机制：

| 错误类型 | 重试策略 |
|---------|---------|
| 上下文溢出 (400 context_length_exceeded) | 截断工具结果 → 压缩历史 → 失败 |
| 限流 (429 rate_limit) | 指数退避等待后重试（最多 3 次） |
| 认证失败 (401) | 尝试切换下一个 provider 的 API key；无可切换时明确报错 |
| 服务器错误 (5xx) | 线性等待重试（最多 2 次） |
| 超时 (timeout) | 增加超时时间重试（30s → 60s → 120s） |
| 模型不可用 (model_not_found / 503) | 自动切换 provider 的 fallback 模型 |

## 范围

- 在 `AnthropicProvider.chat()` 中捕获 SDK 异常，转为类型化 `ProviderError`
- 在 `ContextGuard.async_guard_api_call()` 中按错误类型分发重试策略
- 在 `get_provider()` 中支持运行时切换 provider（用于"切 Key"和"切模型"）
- `AgentRunner.run_turn()` 向上传播结构化错误信息（而非吞掉返回 `""`）

## 非目标

- 不改变 CLI/Gateway 的用户界面
- 不修改工具调用层的 `except Exception`（工具调用错误不需要重试）
- 不影响 memory/session/skill 等模块的 `except Exception`（这些是存储层，非 API 层）
- 不引入新的第三方依赖（使用标准库 `asyncio.sleep`、`time` 等）
