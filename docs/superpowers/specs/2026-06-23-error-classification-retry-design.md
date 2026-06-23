---
comet_change: error-classification-retry
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-23-error-classification-retry
status: final
---

# Error Classification + Differentiated Retry — 技术设计

## 架构

```
AgentRunner.run_turn()
  │  捕获 ProviderError → 可恢复继续 / 不可恢复报错
  └── ContextGuard.async_guard_api_call()
        │  按 ErrorType 分发重试策略
        └── ProviderRouter.current.chat()
              │  返回 Response / 抛 SDK 异常
              └── ErrorMapper.classify(exc) → ProviderError
```

### 分层职责

| 层 | 模块 | 职责 |
|----|------|------|
| 分类 | `agentd/providers/error_mapper.py` | SDK 异常 → `ProviderError`（纯函数） |
| 路由 | `agentd/providers/router.py` | 管理 provider 主备列表，`switch()` |
| 策略 | `agentd/context/context.py` | 按 `ErrorType` 分发重试策略 |
| 传播 | `agentd/agent/runner.py` | 区分可恢复/不可恢复，用户提示 |

## 组件

### ErrorMapper (`agentd/providers/error_mapper.py`)

SDK 异常 → `ProviderError` 映射。三级匹配策略：

1. **精确类型匹配**：`isinstance(exc, anthropic.RateLimitError)` → `RATE_LIMIT`
2. **status_code 回退**：`exc.status_code == 429` → `RATE_LIMIT`（处理非标准 SDK 异常）
3. **消息关键词兜底**：`"rate" in msg and "limit" in msg` → `RATE_LIMIT`（DeepSeek 等非标准 provider）

异常类型映射：

| SDK 异常 | ErrorType |
|----------|-----------|
| `BadRequestError` + "context_length" | `CONTEXT_OVERFLOW` |
| `RateLimitError` | `RATE_LIMIT` |
| `AuthenticationError` / `PermissionDeniedError` | `AUTH_FAILURE` |
| `InternalServerError` + 5xx | `SERVER_ERROR` |
| `APITimeoutError` | `TIMEOUT` |
| `NotFoundError` | `MODEL_UNAVAILABLE` |
| 其他 | `UNKNOWN` |

### ProviderRouter (`agentd/providers/router.py`)

主备模式：`providers[0]` 是主，后续是备。

```python
class ProviderRouter:
    def __init__(self, providers: list[BaseProvider]): ...
    @property
    def current(self) -> BaseProvider: ...
    def switch(self) -> bool: ...    # 切到下一个，返回是否成功
    def reset(self) -> None: ...     # 回到主 provider
```

- `switch()` 成功返回 `True`，无可用时返回 `False`
- `reset()` 在每 turn 开始时调用，确保从主 provider 开始

### 重试策略 (`ContextGuard.async_guard_api_call`)

替换字符串匹配为 `ErrorType` 枚举匹配：

| ErrorType | 最大重试 | 策略 |
|-----------|---------|------|
| `CONTEXT_OVERFLOW` | 2 | 截断工具结果 → 压缩历史 → 抛出 |
| `RATE_LIMIT` | 3 | 指数退避：1s, 2s, 4s |
| `AUTH_FAILURE` | 1 | 切换 provider |
| `SERVER_ERROR` | 2 | 线性退避：2s, 4s |
| `TIMEOUT` | 2 | 增加超时：30s→60s→120s |
| `MODEL_UNAVAILABLE` | 1 | 切换 provider |
| `UNKNOWN` | 0 | 直接抛出，不重试 |

### AgentRunner 错误传播

```python
try:
    response = await self.guard.async_guard_api_call(...)
except ProviderError as exc:
    if exc.error_type in (ErrorType.AUTH_FAILURE, ErrorType.MODEL_UNAVAILABLE):
        # 无可用 provider — 明确报错给用户
        return f"错误: {exc}"
    # 其他未恢复的错误
    logger.exception(...)
    self._rollback(messages)
    return ""
```

## 错误处理

- ErrorMapper 对无法识别的异常归类为 `UNKNOWN`，保留原始异常引用
- ProviderRouter 单 provider 时 `switch()` 返回 `False`，上层报明确错误
- 每次重试前打印用户可见提示（如 `[guard] 限流，2s 后重试...`）
- `UNKNOWN` 错误不重试，避免对未知问题无限重试

## 测试策略

### 单元测试

| 模块 | 测试内容 | 方式 |
|------|---------|------|
| ErrorMapper | 每种 SDK 异常 → 正确 ErrorType | 构造 mock 异常对象 |
| ErrorMapper | DeepSeek 非标准错误 → 关键词兜底 | 构造不带 status_code 的异常 |
| ProviderRouter | 切换、耗尽、reset | 构造 mock provider 列表 |
| ContextGuard | mock provider 注入 ProviderError，验证重试次数和策略 | `AsyncMock` |
| AgentRunner | 验证可恢复/不可恢复错误传播 | mock guard |

### 集成测试

- AUTH_FAILURE → router 切换 → 重试成功
- RATE_LIMIT → 退避等待 → 重试成功
- UNKNOWN → 直接上抛，不重试

### 回归

- 现有 14 个测试全部保持通过
- 上下文溢出行为不变（截断→压缩→失败）

## 风险

| 风险 | 缓解 |
|------|------|
| DeepSeek 不返回标准 Anthropic 错误码 | 三级匹配兜底（类型→status→关键词） |
| 多 provider 配置缺失 | 单 provider 时 AUTH_FAILURE/MODEL_UNAVAILABLE 明确报错 |
| 重试导致用户等待过长 | 每次重试前打印等待提示 |
| 主备切换后行为不一致 | reset() 每 turn 回到主 provider |
