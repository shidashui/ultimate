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
        return messages
```

**调用方只需一行**：

```python
messages = self.guard.preflight(system_prompt, messages)
response = await self.api_call(...)
```

**保留反应式重试作为兜底**：预飞压缩后如果仍溢出（极端情况），保留原有 3 阶段重试逻辑，但设置 `max_retries=1`（只再试一次）。

## 决策 3: 迭代预算 (Iteration Budget)

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
        """消耗一次迭代。返回 True 表示还有剩余。"""
        self.used += 1
        return self.used <= self.max
```

**循环改造**：

```python
budget = IterationBudget(max_iterations=30)
while budget.remaining > 0:
    budget.consume()
    response = await self.guard.async_guard_api_call(...)
    if response.stop_reason == "end_turn":
        return text
    elif response.stop_reason == "tool_use":
        # ... 执行工具，追加结果，继续循环
    else:
        return text
# 预算耗尽 → 强制退出，返回最后文本
return self._extract_text(last_response)
```

**可配置**：`max_iterations` 通过 `config/configs.py` 的 `MAX_TOOL_ITERATIONS` 配置，默认 30。

## 决策 4: 声明式工具注册

### 问题

当前加一个工具涉及两个文件：
1. 写 `agentd/tools/xxx_tools.py`（导出 TOOLS + TOOL_HANDLERS）
2. 改 `agentd/tools/tool_handlers.py`（import + merge）

### 方案

引入 `ToolRegistry` 类，工具文件自注册：

```python
# agentd/tools/registry.py

class ToolRegistry:
    def __init__(self):
        self._tools: list[dict] = []
        self._handlers: dict[str, callable] = {}

    def register(self, name: str, description: str, parameters: dict,
                 handler: callable, toolset: str = "general",
                 check_fn: callable | None = None):
        """声明式注册一个工具。check_fn 返回 False 时工具不可用。"""
        schema = {"name": name, "description": description,
                  "input_schema": {"type": "object", "properties": parameters,
                                   "required": list(parameters.keys())}}
        self._tools.append(schema)
        self._handlers[name] = handler
        # ... 按 toolset 分类存储

    def get_tools(self, enabled_toolsets: set[str] | None = None) -> list[dict]:
        """返回工具列表，可按 toolset 过滤。排除不可用的工具。"""
        ...
```

**工具文件写法**（以 `file_tools.py` 为例）：

```python
# 模块加载时自动注册
from agentd.tools.registry import registry

def _read_file(path: str) -> str: ...
def _write_file(path: str, content: str) -> str: ...

registry.register(name="read_file", description="读取文件",
                  parameters={"path": {"type": "string"}},
                  handler=_read_file, toolset="file")
registry.register(name="write_file", description="写入文件",
                  parameters={"path": {"type": "string"}, "content": {"type": "string"}},
                  handler=_write_file, toolset="file")
```

**`tool_handlers.py` 简化为**：

```python
# 导入即注册（副作用）
from agentd.tools import memory_tools, file_tools, browser_tools, skill_tools

# Container 初始化时
TOOLS = registry.get_tools()
TOOL_HANDLERS = registry.get_handlers()
```

**向后兼容**：现有 `TOOLS` / `TOOL_HANDLERS` 导出保留，由 registry 生成，已有 import 点不受影响。

**平台过滤**：Gateway 可按平台开启/关闭 toolset（如 wechat 平台关掉 file 工具集）：

```python
tools = registry.get_tools(enabled_toolsets={"memory", "browser", "general"})
```

## 决策 5: 统一异步入口

### 问题

`run_turn()` 和 `async_run_turn()` 是两份 ~70 行几乎相同的代码。差异仅在：API 调用方式（`message_client` vs `async_message_client`）和记忆召回（同步 `hybrid_search` vs `asyncio.to_thread`）。

### 方案

**所有路径统一到 async**：

```python
class AgentRunner:
    async def run_turn(self, user_input, messages, store, channel="terminal") -> str:
        """统一异步入口。CLI 用 asyncio.run() 调用，Gateway 用 await。"""
        ...
```

**CLI 适配**（`cli/cli.py`）：

```python
def handle_user_input(self, user_input: str):
    reply = asyncio.run(
        self.runner.run_turn(user_input, self.messages, self.store, "terminal")
    )
    if reply:
        print_assistant(reply)
```

**Gateway 不变**（已经是 async）。

**同步工具适配**：`hybrid_search()` 等 CPU 密集型操作用 `asyncio.to_thread()` 包装，已在 async 版本中实现。

## 文件改动清单

| 文件 | 改动 |
|------|------|
| `agentd/agent/runner.py` | **核心重构**: 统一 async 入口, 缓存 system prompt, 注入记忆到 user message, 迭代预算, 预飞压缩 |
| `agentd/agent/budget.py` | **新建**: `IterationBudget` 类 |
| `agentd/tools/registry.py` | **新建**: `ToolRegistry` 类 |
| `agentd/tools/tool_handlers.py` | 改为 import 触发注册 + registry.get_xxx() |
| `agentd/tools/memory_tools.py` | 改用 registry.register() |
| `agentd/tools/file_tools.py` | 改用 registry.register() |
| `agentd/tools/skill_tools.py` | 改用 registry.register() |
| `agentd/tools/browser_tools.py` | 改用 registry.register()（如有） |
| `agentd/prompt/prompts.py` | `build_system_prompt()` 接受 `memory_context=""` 但不注入（预留给缓存模式），新增 `build_cached_prompt()` 变体 |
| `agentd/context/context.py` | `ContextGuard` 新增 `preflight()` 方法 |
| `agentd/skill/skill.py` | `build_skill_invoke_tool()` 保留但标记 deprecated（由 registry 统一管理） |
| `cli/cli.py` | `handle_user_input()` 改用 `asyncio.run()` |
| `config/configs.py` | 新增 `MAX_TOOL_ITERATIONS` 配置项 |

## 错误处理

| 场景 | 处理 |
|------|------|
| System prompt 缓存构建失败 | 退回到每轮重建（fallback 模式，打印 warning） |
| 预飞压缩失败 | 跳过压缩，直接调 API（让反应式重试兜底） |
| 迭代预算耗尽 | 强制 end_turn，返回最后一条 assistant text |
| Tool registry 注册冲突 | 后注册覆盖先注册，打印 warning |
| asyncio.run() 在已有事件循环中调用 | Gateway 路径不受影响；CLI 独占进程，不会发生 |
