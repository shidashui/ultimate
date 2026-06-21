## Why

当前 Agent 核心循环存在四个结构性问题，源自早期原型阶段的"先跑通"设计惯性：

1. **System prompt 每轮重建** — 记忆召回（`_auto_recall`）结果注入 system prompt 导致其每轮变化，Anthropic prompt cache (KV cache) 完全无法命中。这浪费 token 且增加延迟。
2. **反应式上下文保护** — ContextGuard 在 API 溢出后才截断/压缩，最多浪费 2 次 API 调用（溢出 → 重试 → 再溢出 → 再重试 → 成功）。
3. **无迭代上限** — `while True` 循环无硬上限，LLM 反复调用工具时无法自动中断。
4. **工具注册依赖硬编码 import** — 加一个工具需要写 `xxx_tools.py` + 改 `tool_handlers.py` 的 import 语句。

借鉴 Hermes Agent 的 mature 设计模式，进行针对性重构。

## What Changes

- **System Prompt 缓存** — 首次构建后缓存，不变内容（身份/人格/工具/技能注册表）仅构建一次。记忆上下文从 system prompt 移至 user message，保持 system prompt 稳定以利用 KV cache。
- **预飞上下文压缩** — 在每次 API 调用前估算 token 总量，超过安全阈值（80%）时主动压缩后再调用，从"溢出→重试"变为"检查→压缩→调用"。
- **迭代预算** — 新增 `IterationBudget` 类，限制每轮对话最大工具调用次数，耗尽时强制 `end_turn`。
- **声明式工具注册** — 引入 `ToolRegistry` 类，工具通过 `@register_tool` 装饰器或 `registry.register()` 声明式注册，按 toolset 分类，支持条件可用性 (`check_fn`)。
- **统一异步入口** — 将 `run_turn()` 和 `async_run_turn()` 合并为一个 `run_turn()` 异步方法。CLI 端通过 `asyncio.run()` 调用，Gateway 端直接 `await`，消除 ~70 行重复代码。

## Capabilities

### New Capabilities

- `prompt-caching`: System prompt 构建一次 + 缓存策略。记忆上下文注入 user message 而非 system prompt，保持 system prompt 跨轮稳定。LLM 端 KV cache 全程命中。

### Modified Capabilities

- `agent-tools`: 工具从硬编码 import + 手动合并改为声明式 ToolRegistry。每个工具文件注册自身，按 toolset 分类，支持条件可用性。
- `skill-scheduling`: `skill_invoke` 工具 schema 生成从 `SkillsManager.build_skill_invoke_tool()` 移至 ToolRegistry 动态生成，与其他工具统一 dispatch。
- `system-context`: ContextGuard 压缩策略从反应式（溢出后重试）改为主动式（API 调用前预飞检查 + 提前压缩）。新增 IterationBudget 机制。

## Impact

| 维度 | 影响 |
|------|------|
| **文件改动** | `agentd/agent/runner.py`（核心重构）、`agentd/context/context.py`（preflight + budget）、`agentd/prompt/prompts.py`（缓存策略）、`agentd/tools/tool_handlers.py`（声明式注册）、`agentd/tools/` 下各工具文件（注册方式）、`cli/cli.py`（asyncio.run 适配）、`gateway/gateway.py`（入口统一） |
| **API** | 无外部 API 变更。内部接口：`AgentRunner.run_turn()` 变为 `async`，CLI 调用方式变化 |
| **Breaking** | **BREAKING**: `run_turn()` 从同步改为异步方法，任何直接调用方需适配 |
| **依赖** | 无新增外部依赖。新增 `agentd/tools/registry.py`、`agentd/agent/budget.py` |
| **向后兼容** | CLI 入口 `ultimate chat` 行为不变，内部 `asyncio.run()` 封装对用户透明 |
