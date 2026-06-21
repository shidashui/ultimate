---
comet_change: hermes-agent-refactor
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-21-hermes-agent-refactor
status: final
---

# Hermes Agent Refactor — 技术设计

借鉴 Hermes Agent 的成熟设计模式，对 Agent 核心循环进行结构性重构。

## 1. 架构变更总览

```
之前:
  ┌─────────────┐    每轮重建     ┌──────────────────┐
  │ 用户输入     │ ──────────────▶ │ build_system_    │
  │ + 记忆召回   │                │ prompt(含记忆)    │
  └─────────────┘                └────────┬─────────┘
                                         │
  ┌──────────────────────────────────────┘
  │  while True:                          ← 无上限
  │    static_tools + [skill_invoke]       ← 动态拼装
  │    guard_api_call()                    ← 溢出后重试
  │    → end_turn / tool_use / ...
  └──────────────────────────────────────

之后:
  ┌──────────────────────────────────────────────────┐
  │  _cached_system_prompt (构建一次，不含记忆/时间)  │
  │  ToolRegistry (启动时一次性注册)                  │
  └──────────────────┬───────────────────────────────┘
                     │
  ┌──────────────────▼───────────────────────────────┐
  │  while budget.remaining > 0:                     │
  │    budget.consume()                               │
  │    guard.preflight(system, messages)  ← 主动压缩  │
  │    await guard_api_call(system, messages, tools)  │
  │    → end_turn / tool_use / ...                    │
  │  → 预算耗尽，强制退出                              │
  └──────────────────────────────────────────────────┘

  记忆上下文 + 时间戳 → user message 前缀注入
```

## 2. 决策 1: System Prompt 缓存

### 问题

`build_system_prompt()` 每轮重建，因为 `memory_context` 参数每轮变化。Anthropic prompt cache 0% 命中，每轮重新编码全部 system prompt (~8K tokens)。

### 方案

**缓存不变部分，可变部分注入 user message**。

缓存内容（首次构建，跨轮复用）：
- Layer 1: Identity
- Layer 1.5: Skill Execution Protocol
- Layer 2: Personality (SOUL.md)
- Layer 3: Tool Guidelines (TOOLS.md)
- Layer 4: Skill Registry (名称列表)
- Layer 6: Bootstrap 文件
- Layer 7: Agent ID / Model / Channel / Mode（不含时间）
- Layer 8: Channel Hints

注入 user message 前缀（每轮变化）：
- `[系统时间: YYYY-MM-DD HH:MM UTC]`
- `[记忆上下文]` + 自动召回结果
- `[用户消息]` + 原始输入

**实现**：

```python
class AgentRunner:
    _cached_system_prompt: str | None = None

    async def run_turn(self, user_input, ...):
        memory_context = self.memory_store._auto_recall(user_input)

        if self._cached_system_prompt is None:
            self._cached_system_prompt = build_system_prompt(
                mode="full",
                bootstrap=self.bootstrap_data,
                skill_registry=self.skill_registry,
                channel=channel,
                # 不传 memory_context
            )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        parts = [f"[系统时间: {now}]"]
        if memory_context:
            parts.append(f"[记忆上下文]\n{memory_context}")
        parts.append(f"[用户消息]\n{user_input}")
        user_content = "\n\n".join(parts)

        messages.append({"role": "user", "content": user_content})
```

**错误处理**：缓存构建失败 → 退回到每轮重建（fallback，打印 warning）。

### 风险与缓解

| 风险 | 缓解 |
|------|------|
| 记忆上下文在 user message 中影响力弱于 system prompt | 前缀标记 `[记忆上下文]` + 清晰分隔；实测验证关注度 |
| 长时间运行后缓存中的时间偏差（如 Runtime Context 中其他时间字段） | 唯一时间戳已移入 user message |
| 技能列表变化后缓存过期 | 当前技能列表在启动时发现后不变，无需刷新 |

## 3. 决策 2: 预飞上下文压缩

### 问题

当前 ContextGuard 是反应式：API 调用 → 溢出 → 截断 → 重试 → 溢出 → 压缩 → 重试。最多浪费 2 次 API 调用。

### 方案

**API 调用前主动检查 token 总量，超阈值先压缩**。

```python
class ContextGuard:
    PREFLIGHT_RATIO = 0.8

    def preflight(self, system: str, messages: list[dict]) -> list[dict]:
        total = self.estimate_tokens(system) + self.estimate_messages_tokens(messages)
        if total > self.max_tokens * self.PREFLIGHT_RATIO:
            print_warn(f"  [preflight] {total:,} tokens over threshold, compacting...")
            return self.compact_history(messages)
        return messages
```

**流程变化**：

```
之前:  Call → 💥 → Truncate → Call → 💥 → Compress → Call
之后:  Estimate → Over 80%? → Compress → Call ✓
              ↓ 未超
            Call ✓
```

**兜底保留**：`guard_api_call` 的三阶段重试逻辑保留，`max_retries` 从 2 降为 1（预飞已处理大多数情况，极限溢出只需一次兜底重试）。

### 风险与缓解

| 风险 | 缓解 |
|------|------|
| 估算不准（字符/4 ≠ 真实 token） | 80% 阈值留足裕量；反应式重试保留兜底 |
| 压缩调用额外延迟 | 只超阈值时触发，正常流程零开销 |
| 压缩本身失败 | 跳过压缩，让反应式兜底处理 |

## 4. 决策 3: 迭代预算

### 方案

```python
class IterationBudget:
    def __init__(self, max_iterations: int = 30):
        self.max = max_iterations
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.max - self.used

    def consume(self) -> bool:
        self.used += 1
        return self.used <= self.max
```

**循环改造**：

```python
budget = IterationBudget(self.max_iterations)
while budget.remaining > 0:
    budget.consume()
    # ... LLM 调用 + 工具调度 ...
# 预算耗尽 → 返回最后一条 assistant text 或 "达到迭代上限"
```

**配置**：`config/configs.py` 新增 `MAX_TOOL_ITERATIONS = 30`。

## 5. 决策 4: 声明式工具注册

### 方案

引入 `ToolRegistry` 类，工具通过 `registry.register()` 声明式注册。

```python
# agentd/tools/registry.py

class ToolRegistry:
    def __init__(self):
        self._tools: list[dict] = []
        self._handlers: dict[str, callable] = {}
        self._toolsets: dict[str, list[str]] = {}

    def register(self, *, name: str, description: str,
                 parameters: dict, handler: callable,
                 toolset: str = "general",
                 check_fn: callable | None = None) -> None:
        if check_fn and not check_fn():
            return
        if name in self._handlers:
            print_warn(f"Tool '{name}' 被覆盖")
        schema = {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": parameters,
                "required": list(parameters.keys()),
            },
        }
        self._tools.append(schema)
        self._handlers[name] = handler
        self._toolsets.setdefault(toolset, []).append(name)

    def get_tools(self, enabled_toolsets: set[str] | None = None) -> list[dict]:
        if enabled_toolsets is None:
            return list(self._tools)
        return [t for t in self._tools
                if self._tool_to_toolset(t["name"]) in enabled_toolsets]

    def get_handlers(self) -> dict[str, callable]:
        return dict(self._handlers)

# 全局单例
registry = ToolRegistry()
```

**工具文件改写**（以 `file_tools.py` 为例）：

```python
# 之前
TOOLS = [{"name": "read_file", ...}]
TOOL_HANDLERS = {"read_file": _read_file}

# 之后
from agentd.tools.registry import registry

registry.register(
    name="read_file",
    description="读取文件内容",
    parameters={"path": {"type": "string", "description": "文件路径"}},
    handler=_read_file,
    toolset="file",
)
```

**`tool_handlers.py` 精简为**：

```python
# 导入即注册（利用模块副作用）
from agentd.tools import memory_tools   # noqa: F401
from agentd.tools import file_tools     # noqa: F401
from agentd.tools import browser_tools  # noqa: F401
from agentd.tools import skill_tools    # noqa: F401

from agentd.tools.registry import registry

TOOLS = registry.get_tools()           # 向后兼容
TOOL_HANDLERS = registry.get_handlers() # 向后兼容
```

### skill_invoke 静态化

`skill_invoke` 的工具描述不再动态拼接技能列表，改为静态文本。模型从 system prompt Layer 4 的 `skill_registry` 表格获知可用技能。

```python
# skill_tools.py
registry.register(
    name="skill_invoke",
    description="加载一个已注册的技能模块，获取其完整操作指令。可用技能列表见系统提示词。",
    parameters={
        "name": {"type": "string", "description": "要加载的技能名称"},
        "args": {"type": "string", "description": "传递给技能的可选参数"},
    },
    handler=tool_skill_invoke,
    toolset="skill",
)
```

**删除**：`SkillsManager.build_skill_invoke_tool()` 方法（不再需要动态生成）。

### toolset 分类

| toolset | 工具 | 说明 |
|---------|------|------|
| `file` | read_file, write_file, edit_file, list_directory | 文件操作 |
| `memory` | memory_write, memory_search | 记忆操作 |
| `skill` | skill_invoke | 技能调度 |
| `browser` | (预留) | 浏览器操作 |
| `general` | bash, get_current_time | 通用执行 |

Gateway 可按平台过滤：`registry.get_tools(enabled_toolsets={"memory", "general"})`。

## 6. 决策 5: 统一异步入口

### 问题

`run_turn()`（同步）和 `async_run_turn()`（异步）是两份 ~70 行几乎相同的代码。

### 方案

**所有路径统一到 async `run_turn()`**。

```python
class AgentRunner:
    async def run_turn(self, user_input, messages, store, channel="terminal") -> str:
        """统一异步入口。CLI 端用 asyncio.run() 调用，Gateway 端 await。"""
```

**CLI 适配**：

```python
# cli/cli.py
def handle_user_input(self, user_input: str):
    reply = asyncio.run(
        self.runner.run_turn(user_input, self.messages, self.store, "terminal")
    )
```

**Gateway 适配**：方法名从 `async_run_turn()` → `run_turn()`。

**同步方法适配**：`hybrid_search()` 等 CPU 密集操作用 `asyncio.to_thread()` 包装。

## 7. 文件改动清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `agentd/agent/runner.py` | **重构** | 统一 async，缓存 prompt，记忆注入 user message，预算循环，预飞压缩 |
| `agentd/agent/budget.py` | **新建** | `IterationBudget` 类 |
| `agentd/tools/registry.py` | **新建** | `ToolRegistry` 类 |
| `agentd/tools/tool_handlers.py` | **简化** | import 触发注册 + registry.get_xxx() |
| `agentd/tools/memory_tools.py` | 改写 | `registry.register()` 替代手动导出 |
| `agentd/tools/file_tools.py` | 改写 | 同上 |
| `agentd/tools/skill_tools.py` | 改写 | 同上 + 静态描述 |
| `agentd/tools/browser_tools.py` | 改写 | 同上（如有定义） |
| `agentd/prompt/prompts.py` | 修改 | `memory_context` 参数可选化，移除时间戳注入 |
| `agentd/context/context.py` | 扩展 | `ContextGuard` 新增 `preflight()` |
| `agentd/skill/skill.py` | 删除 | `build_skill_invoke_tool()` 方法 |
| `cli/cli.py` | 适配 | `asyncio.run()` 调用 |
| `gateway/gateway.py` | 适配 | 方法名 `async_run_turn()` → `run_turn()` |
| `config/configs.py` | 新增 | `MAX_TOOL_ITERATIONS = 30` |

## 8. 错误处理矩阵

| 场景 | 处理 |
|------|------|
| System prompt 缓存构建失败 | 退回到每轮重建（fallback 模式，打印 warning） |
| 预飞压缩调用失败 | 跳过压缩，直接调 API（反应式重试兜底） |
| 迭代预算耗尽 | 强制 end_turn，返回最后 assistant text |
| 工具注册同名覆盖 | 打印 warning，后注册覆盖先注册 |
| `asyncio.run()` 嵌套调用 | 不会发生：CLI 独占进程，Gateway 已有事件循环 |
| 原有 `run_turn()` 直接调用方 | **BREAKING**：需改为 `asyncio.run(runner.run_turn(...))` |

## 9. 测试策略

| 场景 | 验证方法 |
|------|---------|
| CLI 启动 | `python ultimate.py chat` 正常启动，命令提示符出现 |
| 基础对话 | 输入消息 → assistant 回复正常 |
| System prompt 缓存 | 日志验证：首次构建 + 后续复用 |
| 记忆注入 user message | 检查 user message 前缀包含 `[记忆上下文]` |
| 预飞压缩触发 | 构造超长上下文（>144K token 估算），观察 preflight 日志 |
| 迭代预算耗尽 | 模拟死循环工具调用序列，30 次后自动终止 |
| 工具注册冲突 | 同名工具覆盖时打印 warning |
| skill_invoke 调度 | `/skills` 列出技能 → LLM 调用 skill_invoke → 加载成功 |
| Gateway 消息 | `python ultimate.py gateway` 启动正常，平台收发正常 |
