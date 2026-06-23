# Design: 错误分类 + 差异化重试

## 架构决策

### 1. 错误分类层次

在 `agentd/providers/base.py` 定义 `ProviderError` 枚举，细化 SDK 异常：

```python
from enum import Enum

class ErrorType(Enum):
    CONTEXT_OVERFLOW = "context_overflow"   # 400 + context_length_exceeded
    RATE_LIMIT       = "rate_limit"         # 429
    AUTH_FAILURE     = "auth_failure"       # 401
    SERVER_ERROR     = "server_error"       # 500-599
    TIMEOUT          = "timeout"            # 网络超时
    MODEL_UNAVAILABLE= "model_unavailable"  # 404 model / 503 service
    UNKNOWN          = "unknown"            # 其他未分类错误

class ProviderError(Exception):
    def __init__(self, error_type: ErrorType, message: str,
                 status_code: int = 0, original: Exception | None = None):
        self.error_type = error_type
        self.status_code = status_code
        self.original = original
        super().__init__(message)
```

### 2. SDK 异常映射（`AnthropicProvider.chat`）

在 `AnthropicProvider.chat()` 中用 try/except 捕获 Anthropic SDK 已知异常类型：

| SDK 异常 | → ErrorType |
|----------|-------------|
| `BadRequestError` + "context_length" | `CONTEXT_OVERFLOW` |
| `RateLimitError` | `RATE_LIMIT` |
| `AuthenticationError` | `AUTH_FAILURE` |
| `InternalServerError` | `SERVER_ERROR` |
| `APITimeoutError` | `TIMEOUT` |
| `NotFoundError` | `MODEL_UNAVAILABLE` |
| 其他 `APIStatusError` | 按 status_code 映射 |
| 非 API 异常 (网络等) | `UNKNOWN` |

### 3. 策略分发（`ContextGuard.async_guard_api_call`）

替换当前基于字符串匹配的 retry 逻辑：

```
async_guard_api_call(system, messages, tools)
  ├── 维护 retry_state {attempt, max_retries, backoff_s}
  ├── try: provider.chat()
  └── catch ProviderError:
        ├── CONTEXT_OVERFLOW → truncate → compact → raise
        ├── RATE_LIMIT        → exponential backoff (1s, 2s, 4s) → retry
        ├── AUTH_FAILURE      → switch_provider() → retry
        ├── SERVER_ERROR      → linear backoff (2s, 4s) → retry
        ├── TIMEOUT           → increase timeout → retry
        ├── MODEL_UNAVAILABLE → switch_provider() → retry
        └── UNKNOWN           → raise (不重试)
```

### 4. Provider 运行时切换（`get_provider` 扩展）

在 Container 中注册多 provider 实例，新增 `ProviderRouter`：

```python
class ProviderRouter:
    def __init__(self, providers: list[BaseProvider]):
        self.providers = providers
        self.current_index = 0

    @property
    def current(self) -> BaseProvider:
        return self.providers[self.current_index]

    def switch(self) -> bool:
        """切换到下一个可用 provider，返回是否成功"""
        if self.current_index + 1 < len(self.providers):
            self.current_index += 1
            return True
        return False  # 无可切换 provider
```

## 数据流

```
AgentRunner.run_turn()
  │  捕获 ProviderError → 根据 error_type 决定是否向上报告
  └── guard.async_guard_api_call()
        │  按 ErrorType 分发策略
        └── provider_router.current.chat()
              │  捕获 SDK 异常 → 映射为 ProviderError
              └── client.messages.create()
```

## 重试参数

| 错误类型 | 最大重试 | 退避策略 | 退避参数 |
|---------|---------|---------|---------|
| CONTEXT_OVERFLOW | 2 | 不等待 | 截断→压缩 |
| RATE_LIMIT | 3 | 指数退避 | 1s, 2s, 4s |
| AUTH_FAILURE | 1 | 不等待 | 切 provider |
| SERVER_ERROR | 2 | 线性退避 | 2s, 4s |
| TIMEOUT | 2 | 不等待 | 30s→60s→120s |
| MODEL_UNAVAILABLE | 1 | 不等待 | 切 provider |

## 风险

| 风险 | 缓解 |
|------|------|
| DeepSeek 不返回标准 Anthropic 错误码 | 增加 `UNKNOWN` 兜底分类 + 错误消息日志 |
| 多 provider 配置缺失 | 单 provider 时 AUTH_FAILURE / MODEL_UNAVAILABLE 直接报错 |
| 重试导致用户等待过长 | 每次重试前打印等待提示 |
