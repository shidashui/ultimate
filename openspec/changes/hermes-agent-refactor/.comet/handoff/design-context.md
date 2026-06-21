# Comet Design Handoff

- Change: hermes-agent-refactor
- Phase: design
- Mode: compact
- Context hash: 90bde2434c066db615af24821415a2e893a1d9cf932ccfa2a4417c9f2cf0957e

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/hermes-agent-refactor/proposal.md

- Source: openspec/changes/hermes-agent-refactor/proposal.md
- Lines: 1-40
- SHA256: 17ef12b925cc56212270f9b74dbc0d2ee546331a7859b482f9e8889738ed7f12

```md
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
```

## openspec/changes/hermes-agent-refactor/design.md

- Source: openspec/changes/hermes-agent-refactor/design.md
- Lines: 1-262
- SHA256: 6863b1938a66a25d0da8100c0b16401d81a4d1798da1f41a82a155c107aa4a45

[TRUNCATED]

```md
## 架构概览

```
                        ┌──────────────────────────┐
                        │     AgentRunner (async)    │
                        │  ┌──────────────────────┐ │
                        │  │ _cached_system_prompt │ │ ← 首次构建, 跨轮复用
                        │  │ IterationBudget      │ │ ← 每轮新建, 防死循环
                        │  └──────────────────────┘ │
                        └──────────┬───────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
   │  Prompt Builder  │  │  PreflightGuard  │  │  ToolRegistry   │
   │  (缓存感知)       │  │  (主动压缩)       │  │  (声明式注册)    │
   └─────────────────┘  └─────────────────┘  └─────────────────┘
```

## 决策 1: System Prompt 缓存策略

### 问题

当前 `build_system_prompt()` 每轮重建，因为 `memory_context` 参数每轮不同（`_auto_recall` 基于当前用户输入检索）。system prompt 变化 → Anthropic prompt cache 失效。

### 方案

**分离不变内容与可变内容**：

```
System Prompt (缓存，只建一次):
  Layer 1: Identity        ← 不变
  Layer 1.5: Skill Protocol ← 不变
  Layer 2: Personality     ← 不变
  Layer 3: Tool Guidelines ← 不变
  Layer 4: Skill Registry  ← 不变 (名称列表不变)
  Layer 6: Bootstrap       ← 不变
  Layer 7: Runtime Context ← 部分变 (时间), 但容忍
  Layer 8: Channel Hints   ← 不变

User Message (每轮动态):
  [Memory Context]         ← 每轮变化
  [用户输入]                ← 每轮变化
```

**实现**：`AgentRunner` 持有 `_cached_system_prompt: str | None`，首次调用 `build_system_prompt(memory_context="")` 构建并缓存。记忆上下文注入到 user message 前缀：

```python
user_content = f"[记忆上下文]\n{memory_context}\n\n[用户消息]\n{user_input}"
```

**权衡**：
- 优点：KV cache 命中率从 0% → ~95%，每次 API 调用省 ~30K token 输入成本，响应延迟降低
- 缺点：记忆上下文放在 user message 中，对模型的影响力略低于 system prompt 顶层。实测通过前缀标记 (`[记忆上下文]`) 和清晰分隔保证关注

## 决策 2: 预飞上下文压缩 (Preflight)

### 问题

当前 ContextGuard 是反应式：调 API → 上下文溢出 → 截断工具结果 → 调 API → 仍溢出 → 压缩历史 → 调 API。最坏情况浪费 2 次 API 调用。

### 方案

**在 API 调用前主动检查 + 压缩**：

```
当前:  Call → 💥 → Truncate → Call → 💥 → Compress → Call

改为:  Estimate → Over 80%? → Compress → Call ✓
```

```python
class ContextGuard:
    PREFLIGHT_RATIO = 0.8  # 80% 阈值触发压缩

    def preflight(self, system: str, messages: list[dict]) -> list[dict]:
        """预飞检查：估算 token，超阈值主动压缩后返回。"""
        total = self.estimate_tokens(system) + self.estimate_messages_tokens(messages)
        if total > self.max_tokens * self.PREFLIGHT_RATIO:
            return self.compact_history(messages)
```

Full source: openspec/changes/hermes-agent-refactor/design.md

## openspec/changes/hermes-agent-refactor/tasks.md

- Source: openspec/changes/hermes-agent-refactor/tasks.md
- Lines: 1-63
- SHA256: ebe319e363a9f8de780d99b79eafaf930ffd1a4423a8cd5240e2ee6a79920280

```md
## 实施任务

### 阶段 1: 基础设施 (独立，先做)

- [ ] **Task 1: 创建 IterationBudget**
  - 新建 `agentd/agent/budget.py`
  - `IterationBudget(max_iterations)` 类：`remaining` 属性, `consume()` 方法
  - `config/configs.py` 新增 `MAX_TOOL_ITERATIONS = 30`

- [ ] **Task 2: 创建 ToolRegistry**
  - 新建 `agentd/tools/registry.py`
  - `ToolRegistry` 类：`register()`, `get_tools()`, `get_handlers()`, `get_toolsets()`
  - 支持 `toolset` 分类和 `check_fn` 条件可用性
  - 同名工具覆盖时打印 warning

### 阶段 2: 工具迁移 (依赖 Task 2)

- [ ] **Task 3: 迁移工具文件到声明式注册**
  - `memory_tools.py`: 改为 `registry.register()` 调用
  - `file_tools.py`: 同上
  - `skill_tools.py`: 同上
  - `browser_tools.py`: 同上（如有工具定义）
  - `tool_handlers.py`: 改为 import 触发注册 + `registry.get_tools()` / `registry.get_handlers()`
  - 保留 `TOOLS` / `TOOL_HANDLERS` 模块级导出变量（由 registry 生成，向后兼容）

### 阶段 3: ContextGuard 升级 (独立)

- [ ] **Task 4: ContextGuard 新增预飞压缩**
  - `agentd/context/context.py`: `ContextGuard` 新增 `preflight(system, messages) -> list[dict]`
  - 阈值 `PREFLIGHT_RATIO = 0.8`，超阈值调用 `compact_history()`
  - 保留原有反应式重试逻辑作为兜底（`max_retries` 可从 2 减为 1）
  - 同步和异步版本均支持

### 阶段 4: AgentRunner 核心重构 (依赖 Tasks 1-4)

- [ ] **Task 5: AgentRunner 核心重构**
  - `agentd/agent/runner.py`:
    - 删除 `run_turn()` 同步方法，`async_run_turn()` 重命名为 `run_turn()`
    - 新增 `_cached_system_prompt: str | None`，首次构建后缓存
    - `build_system_prompt()` 不再传 `memory_context`（记忆注入 user message）
    - user message 前缀注入记忆上下文
    - 循环引入 `IterationBudget`：`while budget.remaining > 0: budget.consume()`
    - API 调用前执行 `guard.preflight()`
    - 预算耗尽时返回最后一条 assistant text

### 阶段 5: 入口适配 (依赖 Task 5)

- [ ] **Task 6: CLI 和 Gateway 适配**
  - `cli/cli.py`: `handle_user_input()` 改用 `asyncio.run(self.runner.run_turn(...))`
  - `cli/cli.py`: `/prompt` 命令适配新的 prompt 构建方式
  - `gateway/gateway.py`: `async_run_turn()` 调用改为 `run_turn()`（方法名变化）
  - `agentd/prompt/prompts.py`: `build_system_prompt()` 不再强制依赖 `memory_context` 参数

### 阶段 6: 验证

- [ ] **Task 7: 功能验证**
  - CLI 启动测试：`ultimate chat` 正常启动
  - 基础对话：用户消息 → assistant 回复
  - 工具调用：工具可被 LLM 调用并返回结果
  - 技能加载：`skill_invoke` 正常注册和调度
  - 迭代预算：模拟死循环场景，验证 30 次后自动终止
  - 预飞压缩：长对话触发压缩，验证压缩后正常继续
  - Gateway 验证：`ultimate gateway` 启动正常，平台消息收发正常
```

## openspec/changes/hermes-agent-refactor/specs/agent-tools/spec.md

- Source: openspec/changes/hermes-agent-refactor/specs/agent-tools/spec.md
- Lines: 1-43
- SHA256: a53ad336139f778f8e19b81f4a3e3af66f9a997f761e9165b42f59f34dbb010e

```md
# Agent Tools — Delta: 声明式工具注册

## 变更说明

工具注册机制从硬编码 import + 手动合并改为声明式 `ToolRegistry`。此变更修改 `agent-tools` spec 中关于工具注册和发现的部分。

## 修改的要求

### AT-REGISTRY: 声明式工具注册 (新增)

工具通过 `ToolRegistry.register()` 声明式注册，替代手动构造 schema 字典和手动合并 TOOLS 列表。

- **AT-REG-1**: 系统提供全局 `ToolRegistry` 单例 (`agentd.tools.registry.registry`)
- **AT-REG-2**: `registry.register(name, description, parameters, handler, toolset)` 接受工具定义并自动生成 Anthropic API 兼容的 tool schema
- **AT-REG-3**: 工具按 `toolset` 分类（`file`, `memory`, `skill`, `browser`, `general`）
- **AT-REG-4**: `registry.get_tools(enabled_toolsets=None)` 返回工具列表，可按 toolset 过滤
- **AT-REG-5**: `registry.get_handlers()` 返回 `{name: handler}` 映射
- **AT-REG-6**: 同名工具注册时打印 warning，后注册覆盖先注册
- **AT-REG-7**: 支持 `check_fn` 参数：返回 `False` 时工具静默跳过（条件可用性）

### AT-IMPORT: 工具自动发现 (修改)

工具文件的导入即触发注册（利用 Python 模块加载副作用）。

- **AT-IMP-1**: `tool_handlers.py` 通过 import 语句触发各工具模块加载和注册
- **AT-IMP-2**: 新增工具只需创建 `xxx_tools.py` 并在 `tool_handlers.py` 中 import，无需手动合并 TOOLS 列表
- **AT-IMP-3**: 向后兼容：保留模块级 `TOOLS` 和 `TOOL_HANDLERS` 导出变量

### AT-SKILL-STATIC: skill_invoke 静态 schema (修改)

`skill_invoke` 的工具描述不再动态拼接技能列表。

- **AT-SKILL-1**: `skill_invoke` 工具的 `description` 字段为静态文本，不包含技能名称列表
- **AT-SKILL-2**: 技能名称列表仅在 system prompt Layer 4 的 `skill_registry` 中展示
- **AT-SKILL-3**: 删除 `SkillsManager.build_skill_invoke_tool()` 方法

## 验收场景

1. **注册工具**: 通过 `registry.register()` 注册 → `registry.get_tools()` 返回对应 schema
2. **按 toolset 过滤**: `registry.get_tools(enabled_toolsets={"memory"})` 只返回 memory 工具
3. **同名覆盖 warning**: 注册同名工具 → 控制台输出 warning
4. **条件可用**: `check_fn=lambda: False` → 工具不被注册
5. **向后兼容**: `from agentd.tools.tool_handlers import TOOLS, TOOL_HANDLERS` 正常工作
```

## openspec/changes/hermes-agent-refactor/specs/prompt-caching/spec.md

- Source: openspec/changes/hermes-agent-refactor/specs/prompt-caching/spec.md
- Lines: 1-42
- SHA256: 72da5e79332cd1c34315222985d1e8adefd17bd6392f9180e708110f67cbc4ff

```md
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
```

## openspec/changes/hermes-agent-refactor/specs/skill-scheduling/spec.md

- Source: openspec/changes/hermes-agent-refactor/specs/skill-scheduling/spec.md
- Lines: 1-32
- SHA256: bfcf1f0e8ae4c77495b1a13c75dac9f6aeda8fc0bb02989fd23c54ad2c5fb053

```md
# Skill Scheduling — Delta: skill_invoke 静态化

## 变更说明

`skill_invoke` 工具的描述注册从"每轮动态拼接"改为"静态注册一次"。此变更简化 skill-scheduling 的实现，删除 `build_skill_invoke_tool()` 的动态生成逻辑。

## 修改的要求

### SS-STATIC: skill_invoke 静态注册 (修改)

`skill_invoke` 作为普通工具注册到 ToolRegistry，不在每轮重建 schema。

- **SS-STATIC-1**: `skill_tools.py` 中使用 `registry.register()` 注册 `skill_invoke`，与其他工具一致
- **SS-STATIC-2**: `skill_invoke` 的 description 为静态文本："加载一个已注册的技能模块，获取其完整操作指令。可用技能列表见系统提示词。"
- **SS-STATIC-3**: `SkillsManager.build_skill_invoke_tool()` 方法删除
- **SS-STATIC-4**: AgentRunner 不再调用 `skills_mgr.build_skill_invoke_tool()` 进行动态 tools 组装
- **SS-STATIC-5**: system prompt Layer 4 的 `skill_registry` 表格仍然是技能名称的唯一权威来源

### SS-COMPAT: 向后兼容 (不变)

以下要求不受影响：
- Progressive Disclosure 三层模型（L1 registry / L2 on-demand / L3 resources）
- Skill Execution Protocol 元指令（Layer 1.5）
- `tool_skill_invoke()` handler 逻辑（按名查找、返回正文）
- `SkillsManager.get_skill()` 和 `format_skill_registry()` 方法

## 验收场景

1. **skill_invoke 注册**: CLI 启动时 `skill_invoke` 出现在工具列表中
2. **技能加载**: LLM 调用 `skill_invoke(name="comet")` → 返回对应 SKILL.md 正文
3. **未知技能**: 调用不存在的技能名 → 返回可用列表
4. **不动态重建**: AgentRunner 不再每轮调用 `build_skill_invoke_tool()`
```

## openspec/changes/hermes-agent-refactor/specs/system-context/spec.md

- Source: openspec/changes/hermes-agent-refactor/specs/system-context/spec.md
- Lines: 1-43
- SHA256: 10ce558575a6ea9506d33f340a3d28934593ec48fb7a763a799743f848c858bb

```md
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
```

