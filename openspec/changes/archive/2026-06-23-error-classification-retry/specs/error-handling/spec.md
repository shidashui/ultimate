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

#### Scenario: 超时增加超时时间
- **GIVEN** provider 抛出 `TIMEOUT` 错误
- **WHEN** 重试时
- **THEN** 超时时间依次增加为 30s→60s→120s

#### Scenario: 模型不可用切换 provider
- **GIVEN** provider 抛出 `MODEL_UNAVAILABLE` 错误
- **WHEN** `ProviderRouter.switch()` 返回 True
- **THEN** 切换到备选 provider 重试

#### Scenario: UNKNOWN 不重试
- **GIVEN** provider 抛出 `UNKNOWN` 错误
- **WHEN** `ContextGuard.async_guard_api_call()` 捕获该错误
- **THEN** 直接向上抛出，不进行任何重试

---

### Requirement: ProviderRouter 主备切换
`ProviderRouter` MUST 实现主备模式：`providers[0]` 为主，后续为备。

#### Scenario: 从主切换到备
- **GIVEN** ProviderRouter 有两个 provider
- **WHEN** 调用 `switch()`
- **THEN** `current` 返回第二个 provider，`switch()` 返回 True

#### Scenario: 最后一个 provider 无法切换
- **GIVEN** ProviderRouter 仅有一个 provider
- **WHEN** 调用 `switch()`
- **THEN** 返回 False，`current` 不变

#### Scenario: reset 回到主
- **GIVEN** 已切换到备选 provider
- **WHEN** 调用 `reset()`
- **THEN** `current` 返回第一个（主）provider
