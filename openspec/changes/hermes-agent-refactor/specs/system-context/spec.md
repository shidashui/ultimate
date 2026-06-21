# System Context — Delta: 预飞压缩 + 迭代预算

## 变更说明

ContextGuard 从纯反应式上下文保护升级为主动预飞检查 + 反应式兜底。新增 IterationBudget 机制防止无限工具循环。

## 修改的要求

### SC-PREFLIGHT: 预飞上下文压缩 (新增)

API 调用前主动估算 token 总量，超阈值时先压缩后调用。

- **SC-PF-1**: `ContextGuard.preflight(system, messages)` 估算 system + messages 总 token
- **SC-PF-2**: 超过 `max_tokens * 0.8` 阈值时调用 `compact_history()` 压缩
- **SC-PF-3**: 未超阈值时直接返回原 messages，零开销
- **SC-PF-4**: 预飞压缩失败时跳过压缩，让反应式重试兜底
- **SC-PF-5**: `guard_api_call()` 的 `max_retries` 从 2 降为 1（预飞已处理大多数情况）

### SC-BUDGET: 迭代预算 (新增)

每轮对话限制最大工具调用次数，防止无限循环。

- **SC-BUD-1**: 系统提供 `IterationBudget(max_iterations)` 类
- **SC-BUD-2**: `budget.remaining` 属性返回剩余次数
- **SC-BUD-3**: `budget.consume()` 消耗一次并返回是否还有剩余
- **SC-BUD-4**: 默认上限 `MAX_TOOL_ITERATIONS = 30`，通过 `config/configs.py` 配置
- **SC-BUD-5**: 预算耗尽时强制退出工具循环，返回最后一条 assistant text

### SC-RETRY: 反应式重试保留 (修改)

原有三阶段重试逻辑保留但降级。

- **SC-RET-1**: 第 0 次尝试（正常调用）、第 1 次尝试（截断工具结果）保留
- **SC-RET-2**: 第 2 次尝试（压缩历史）由预飞替代，不再单独重试
- **SC-RET-3**: 所有重试失败仍抛出 `RuntimeError`

## 验收场景

1. **预飞不触发**: 短对话 → API 调用前 preflight 检查通过 → 不压缩 → 正常调用
2. **预飞触发**: 构造 >80% 阈值上下文 → preflight 触发 compact → 消息数减少
3. **预算正常**: 3 次工具调用后 end_turn → budget.remaining = 27
4. **预算耗尽**: 30+ 次工具调用 → 强制退出 → 返回文本
5. **兜底重试**: 预飞后仍溢出 → guard_api_call 第 1 次重试截断 → 成功
