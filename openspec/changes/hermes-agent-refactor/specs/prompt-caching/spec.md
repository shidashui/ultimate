# Prompt Caching — System Prompt 构建一次 + 缓存策略

## 定义

System prompt 首次构建后缓存，跨轮复用。记忆上下文和系统时间从 system prompt 分离，注入 user message 前缀。保持 system prompt 跨轮稳定以利用 LLM 端 KV cache。

## 要求

### PC-1: System Prompt 缓存

System prompt 在 AgentRunner 生命周期内仅构建一次（首次调用时），后续调用复用缓存。

- **PC-1.1**: AgentRunner 持有 `_cached_system_prompt: str | None`，初始为 `None`
- **PC-1.2**: 首次 `run_turn()` 调用时构建并赋值，后续直接使用缓存
- **PC-1.3**: `build_system_prompt()` 不再接收 `memory_context` 参数（或接收空字符串作为默认值）

### PC-2: 记忆上下文注入 user message

记忆召回结果注入到 user message 前缀，而非 system prompt。

- **PC-2.1**: user message 格式为 `[系统时间: <timestamp>]\n\n[记忆上下文]\n<recalled>\n\n[用户消息]\n<user_input>`
- **PC-2.2**: 无记忆上下文时，省略 `[记忆上下文]` 区块
- **PC-2.3**: 注入格式使用前缀标记 (`[系统时间]`, `[记忆上下文]`, `[用户消息]`) 以保证模型对结构清晰感知

### PC-3: 时间戳分离

系统时间从 system prompt 移除，注入 user message。

- **PC-3.1**: `build_system_prompt()` 的 Layer 7 Runtime Context 不再包含时间戳
- **PC-3.2**: 每轮 user message 前缀包含当前 UTC 时间

### PC-4: 缓存失效与 fallback

- **PC-4.1**: 缓存构建失败时，退回到每轮重建模式，打印 warning 日志
- **PC-4.2**: 当需要失效缓存时（如技能列表变化），调用方设置 `_cached_system_prompt = None` 触发下次重建

## 验收场景

1. **缓存命中**: 首轮对话构建 system prompt → 第二轮使用缓存，不重复构建
2. **记忆注入**: user message 前缀包含 `[记忆上下文]` 区块，内容来自 `_auto_recall`
3. **时间准确**: 每轮 user message 前缀包含当前 UTC 时间
4. **Fallback**: 构建失败时自动退回到每轮重建，不影响对话功能
