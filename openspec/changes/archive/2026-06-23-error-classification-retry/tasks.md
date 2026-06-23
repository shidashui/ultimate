# Tasks: 错误分类 + 差异化重试

## 实现任务

### Task 1: 定义类型化错误 (`agentd/providers/base.py`)

- [x] 在 `base.py` 中新增 `ErrorType` 枚举类
- [x] 新增 `ProviderError` 异常类（包含 error_type, status_code, original）
- [x] 编写单元测试：验证 ErrorType 枚举值、ProviderError 构造

### Task 2: ErrorMapper SDK 异常映射 (`agentd/providers/error_mapper.py`)

- [x] 创建 `error_mapper.py`：`classify()` 函数，三级匹配策略（精确类型 → status_code → 关键词）
- [x] 已分类的 ProviderError 直接透传
- [x] 非 API 异常（网络错误等）归类为 `UNKNOWN`
- [x] 编写单元测试：19 个测试覆盖类型匹配、status_code 回退、关键词兜底、透传、元数据

### Task 3: ProviderRouter 主备切换 (`agentd/providers/router.py`)

- [x] 新增 `ProviderRouter` 类，管理多 provider 实例
- [x] 支持 `switch()` 切换到下一个 provider
- [x] 新增 `get_all_providers()` 工厂函数
- [x] 更新 Container 注册逻辑：根据 config 创建所有 provider
- [x] 编写单元测试：9 个测试验证切换逻辑、单 provider 边界、reset

### Task 4: ContextGuard 策略分发重写 (`agentd/context/context.py`)

- [x] 重写 `async_guard_api_call()` 的错误处理逻辑
- [x] 替换字符串匹配为 `ProviderError.error_type` 类型匹配
- [x] 实现各错误类型的重试策略（指数退避/线性退避/切 provider/增加超时）
- [x] 重试前打印用户可见提示
- [x] 编写单元测试：12 个 mock 测试验证各策略分发行为

### Task 5: AgentRunner 结构化错误传播 (`agentd/agent/runner.py`)

- [x] `run_turn()` 中捕获 `ProviderError`，区分可恢复/不可恢复
- [x] 不可恢复错误（AUTH_FAILURE、MODEL_UNAVAILABLE）→ 明确报错
- [x] 可恢复错误 → 允许 guard 重试后继续
- [x] 每 turn 开始 reset router 回到主 provider
- [x] 保持现有 rollback 行为

### Task 6: 集成验证

- [x] 运行全部测试，56/56 通过，无回归
- [x] 编写集成测试：full retry chain + auth failure fatal
- [x] Build verification 通过
