# Comet Design Handoff

- Change: error-classification-retry
- Phase: design
- Mode: compact
- Context hash: bd455d4c430dccae5115ce83b2e9d8982ea8ac16b0dbc967e61c4c1acc3d2490

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/error-classification-retry/proposal.md

- Source: openspec/changes/error-classification-retry/proposal.md
- Lines: 1-39
- SHA256: 8ad1d87dcb46f6de41d021609082906f745ddf1545c39a68146fb8774b956108

```md
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
```

## openspec/changes/error-classification-retry/design.md

- Source: openspec/changes/error-classification-retry/design.md
- Lines: 1-114
- SHA256: aeb7a28a22d100da7f274f91b48fc835cb1ec50c564c2063a91b98ed56c5917e

[TRUNCATED]

```md
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
```

Full source: openspec/changes/error-classification-retry/design.md

## openspec/changes/error-classification-retry/tasks.md

- Source: openspec/changes/error-classification-retry/tasks.md
- Lines: 1-45
- SHA256: f6b675f1b3055b67d9eab6f69be43bf94b80f33574e57e20d53963654016dbd0

```md
# Tasks: 错误分类 + 差异化重试

## 实现任务

### Task 1: 定义类型化错误 (`agentd/providers/base.py`)

- [ ] 在 `base.py` 中新增 `ErrorType` 枚举类
- [ ] 新增 `ProviderError` 异常类（包含 error_type, status_code, original）
- [ ] 编写单元测试：验证 ErrorType 枚举值、ProviderError 构造

### Task 2: SDK 异常映射 (`agentd/providers/anthropic.py`)

- [ ] 在 `AnthropicProvider.chat()` 中捕获 Anthropic SDK 异常
- [ ] 按异常类型 + status_code + 错误消息映射为 `ProviderError`
- [ ] 非 API 异常（网络错误等）归类为 `UNKNOWN`
- [ ] 编写单元测试：模拟各类 SDK 异常，验证映射正确

### Task 3: Provider 运行时切换 (`agentd/providers/__init__.py`)

- [ ] 新增 `ProviderRouter` 类，管理多 provider 实例
- [ ] 支持 `switch()` 切换到下一个 provider
- [ ] 修改 `get_provider()` 或新增工厂函数支持返回 router
- [ ] 更新 Container 注册逻辑：根据 config 创建所有 provider
- [ ] 编写单元测试：验证切换逻辑、单 provider 边界

### Task 4: 策略分发重试 (`agentd/context/context.py`)

- [ ] 重写 `async_guard_api_call()` 的错误处理逻辑
- [ ] 替换字符串匹配为 `ProviderError.error_type` 类型匹配
- [ ] 实现各错误类型的重试策略（指数退避/线性退避/切 provider/增加超时）
- [ ] 重试前打印用户可见提示
- [ ] 编写单元测试：mock provider 注入特定错误，验证重试行为

### Task 5: Runner 结构化错误传播 (`agentd/agent/runner.py`)

- [ ] `run_turn()` 中捕获 `ProviderError`，区分可恢复/不可恢复
- [ ] 不可恢复错误（AUTH_FAILURE 无可切换、UNKNOWN）→ 明确报错
- [ ] 可恢复错误 → 允许 guard 重试后继续
- [ ] 保持现有 rollback 行为

### Task 6: 集成验证

- [ ] 运行全部现有测试，确认无回归
- [ ] 编写集成测试：模拟端到端错误场景
- [ ] 手动测试：确认错误提示信息清晰可操作
```

## openspec/changes/error-classification-retry/specs/error-handling/spec.md

- Source: openspec/changes/error-classification-retry/specs/error-handling/spec.md
- Lines: 1-115
- SHA256: 0d70f34d0274316d641815ed27973e279832ca8d9b93c9c1e5875dee14924ca5

[TRUNCATED]

```md
# Error Handling — Delta Spec

## ADDED Requirements

### Requirement: ErrorType 枚举
系统 MUST 定义 `ErrorType` 枚举，包含以下七种错误类型：
`CONTEXT_OVERFLOW`, `RATE_LIMIT`, `AUTH_FAILURE`, `SERVER_ERROR`,
`TIMEOUT`, `MODEL_UNAVAILABLE`, `UNKNOWN`。

#### Scenario: ErrorType 枚举值完整性
- **GIVEN** 需要表示限流错误
- **WHEN** 使用 `ErrorType.RATE_LIMIT`
- **THEN** 枚举值为 `"rate_limit"`

#### Scenario: ProviderError 包含完整上下文
- **GIVEN** SDK 返回 429 状态码
- **WHEN** 构造 `ProviderError(ErrorType.RATE_LIMIT, "too many requests", status_code=429, original=exc)`
- **THEN** 所有字段可正确访问

---

### Requirement: ErrorMapper 三级匹配
ErrorMapper `classify()` 函数 MUST 按三级优先级匹配异常：
1. 精确类型匹配（`isinstance` 检查 SDK 异常类型）
2. status_code 回退（当异常有 `status_code` 属性时）
3. 消息关键词兜底（检查错误消息字符串）

#### Scenario: 标准 SDK 异常精确匹配
- **GIVEN** Anthropic SDK 抛出 `RateLimitError`
- **WHEN** 调用 `ErrorMapper.classify(exc)`
- **THEN** 返回 `ProviderError` 且 `error_type == ErrorType.RATE_LIMIT`

#### Scenario: 非标准异常 status_code 回退
- **GIVEN** 异常不含标准 SDK 类型但 `status_code == 429`
- **WHEN** 调用 `ErrorMapper.classify(exc)`
- **THEN** 返回 `ProviderError` 且 `error_type == ErrorType.RATE_LIMIT`

#### Scenario: 消息关键词兜底
- **GIVEN** 异常无 `status_code` 属性，消息为 `"rate limit exceeded"`
- **WHEN** 调用 `ErrorMapper.classify(exc)`
- **THEN** 返回 `ProviderError` 且 `error_type == ErrorType.RATE_LIMIT`

#### Scenario: 无法识别归为 UNKNOWN
- **GIVEN** 无法匹配任何已知类型
- **WHEN** 调用 `ErrorMapper.classify(exc)`
- **THEN** 返回 `ProviderError` 且 `error_type == ErrorType.UNKNOWN`

---

### Requirement: ContextGuard 策略分发
`ContextGuard.async_guard_api_call()` MUST 根据 `ErrorType` 分发差异化重试策略。

#### Scenario: 上下文溢出两级重试
- **GIVEN** provider 抛出 `CONTEXT_OVERFLOW` 错误
- **WHEN** 第一次重试
- **THEN** 截断过大的工具结果后重试
- **WHEN** 第二次重试
- **THEN** 通过 LLM 摘要压缩历史后重试
- **WHEN** 第三次重试
- **THEN** 抛出异常

#### Scenario: 限流指数退避
- **GIVEN** provider 抛出 `RATE_LIMIT` 错误
- **WHEN** 重试时
- **THEN** 等待 2^attempt 秒后重试，最多 3 次

#### Scenario: 认证失败切换 provider
- **GIVEN** provider 抛出 `AUTH_FAILURE` 错误
- **WHEN** `ProviderRouter.switch()` 返回 True
- **THEN** 切换到备选 provider 重试

#### Scenario: 认证失败无备选报错
- **GIVEN** provider 抛出 `AUTH_FAILURE` 错误
- **WHEN** `ProviderRouter.switch()` 返回 False（无备选）
- **THEN** 向上抛出 `ProviderError`

#### Scenario: 服务器错误线性重试
- **GIVEN** provider 抛出 `SERVER_ERROR` 错误
- **WHEN** 重试时
- **THEN** 等待 2*(attempt+1) 秒后重试，最多 2 次
```

Full source: openspec/changes/error-classification-retry/specs/error-handling/spec.md

