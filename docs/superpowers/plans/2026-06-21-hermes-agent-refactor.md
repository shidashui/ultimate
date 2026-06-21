---
change: hermes-agent-refactor
design-doc: docs/superpowers/specs/2026-06-21-hermes-agent-refactor-design.md
base-ref: 5914fed16e00f4768bfc39ada2933c657c2e338d
archived-with: 2026-06-21-hermes-agent-refactor
---

# Hermes Agent Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Agent core loop: system prompt caching, preflight compression, iteration budget, declarative tool registry, unified async entry.

**Architecture:** Two new files (registry, budget) + incremental changes to existing files. Tasks 1-2 are independent infrastructure; Task 3 migrates tools to registry; Task 4 upgrades ContextGuard; Task 5 is the core runner refactor (depends on 1-4); Task 6 adapts entry points; Task 7 verifies.

**Tech Stack:** Python 3.10+, asyncio, Anthropic SDK

## Global Constraints

- Backward compatible: CLI `ultimate chat` must work identically after refactor
- Gateway must continue to handle multi-platform messages
- All existing tool functionality preserved (file, memory, browser, skill, bash)
- `TOOLS` / `TOOL_HANDLERS` module-level exports retained for backward compat
- No new external dependencies

archived-with: 2026-06-21-hermes-agent-refactor
---

### Task 1: IterationBudget

**Files:**
- Create: `agentd/agent/budget.py`
- Modify: `config/configs.py`

**Interfaces:**
- Produces: `IterationBudget(max_iterations)` class with `remaining` property, `consume() -> bool`
- Produces: `MAX_TOOL_ITERATIONS = 30` in config

- [ ] **Step 1: Write IterationBudget class**

```python
# agentd/agent/budget.py

class IterationBudget:
    """工具循环迭代预算，防止无限循环。"""

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

- [ ] **Step 2: Add MAX_TOOL_ITERATIONS to config**

```python
# config/configs.py — add after MAX_SKILLS_PROMPT = 30000
MAX_TOOL_ITERATIONS = 30
```

- [ ] **Step 3: Commit**

```bash
git add agentd/agent/budget.py config/configs.py
git commit -m "feat: add IterationBudget and MAX_TOOL_ITERATIONS config"
```

archived-with: 2026-06-21-hermes-agent-refactor
---

### Task 2: ToolRegistry — Declarative Tool Registration

**Files:**
- Create: `agentd/tools/registry.py`

**Interfaces:**
- Produces: `ToolRegistry` class with `register()`, `get_tools()`, `get_handlers()`
- Produces: global `registry` singleton

- [ ] **Step 1: Write ToolRegistry class**

```python
# agentd/tools/registry.py
from utils.print_tools import print_warn


class ToolRegistry:
    """声明式工具注册表。"""

    def __init__(self):
        self._tools: list[dict] = []
        self._handlers: dict[str, callable] = {}
        self._tool_to_toolset: dict[str, str] = {}
        self._toolsets: dict[str, list[str]] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, dict],
        handler: callable,
        toolset: str = "general",
        check_fn: callable | None = None,
    ) -> None:
        """声明式注册一个工具。

        Args:
            name: 工具名称（唯一标识，与 Anthropic API tool name 对应）
            description: 工具描述（注入 tool schema）
            parameters: 参数定义 dict，key 为参数名，value 为 {"type": "...", "description": "..."}
            handler: 工具执行函数，接受关键字参数，返回字符串
            toolset: 工具集分类（file, memory, skill, browser, general）
            check_fn: 条件可用性检查，返回 False 时跳过注册
        """
        if check_fn is not None and not check_fn():
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
        self._tool_to_toolset[name] = toolset
        self._toolsets.setdefault(toolset, []).append(name)

    def get_tools(self, enabled_toolsets: set[str] | None = None) -> list[dict]:
        """返回工具 schema 列表，可按 toolset 过滤。"""
        if enabled_toolsets is None:
            return list(self._tools)
        return [
            t for t in self._tools
            if self._tool_to_toolset.get(t["name"]) in enabled_toolsets
        ]

    def get_handlers(self) -> dict[str, callable]:
        """返回 {name: handler} 映射。"""
        return dict(self._handlers)

    def get_toolsets(self) -> dict[str, list[str]]:
        """返回 {toolset: [tool_names]} 映射。"""
        return {k: list(v) for k, v in self._toolsets.items()}


# 全局单例 — 模块加载时创建，工具文件 import 时自注册
registry = ToolRegistry()
```

- [ ] **Step 2: Commit**

```bash
git add agentd/tools/registry.py
git commit -m "feat: add ToolRegistry — declarative tool registration"
```

archived-with: 2026-06-21-hermes-agent-refactor
---

### Task 3: Migrate Tools to Registry

**Files:**
- Modify: `agentd/tools/memory_tools.py`
- Modify: `agentd/tools/file_tools.py`
- Modify: `agentd/tools/browser_tools.py`
- Modify: `agentd/tools/skill_tools.py`
- Modify: `agentd/tools/tool_handlers.py`

**Interfaces:**
- Consumes: `ToolRegistry.registry` (from Task 2)
- Produces: All tools registered via `registry.register()`; backward-compatible `TOOLS` / `TOOL_HANDLERS` exports

- [ ] **Step 1: Migrate memory_tools.py**

Add `registry.register()` calls and keep `TOOLS` / `TOOL_HANDLERS` exports (but derive from registry). The handler functions stay unchanged.

Replace the bottom section (from line 38 `TOOLS = [` to end) with:

```python
from agentd.tools.registry import registry

registry.register(
    name="memory_write",
    description=(
        "Save an important fact or observation to long-term memory. "
        "Use when you learn something worth remembering about the user or context."
    ),
    parameters={
        "content": {"type": "string", "description": "The fact or observation to remember."},
        "category": {"type": "string", "description": "Category: preference, fact, context, etc."},
    },
    handler=tool_memory_write,
    toolset="memory",
)

registry.register(
    name="memory_search",
    description="Search stored memories for relevant information, ranked by similarity.",
    parameters={
        "query": {"type": "string", "description": "Search query."},
        "top_k": {"type": "integer", "description": "Max results. Default: 5."},
    },
    handler=tool_memory_search,
    toolset="memory",
)

# 向后兼容的模块级导出
TOOLS = [t for t in registry.get_tools() if t["name"] in ("memory_write", "memory_search")]
TOOL_HANDLERS: dict[str, Any] = {
    "memory_write": tool_memory_write,
    "memory_search": tool_memory_search,
}
```

- [ ] **Step 2: Migrate file_tools.py**

Replace the bottom section (from line 200 `TOOLS = [` to line 339 end) with:

```python
from agentd.tools.registry import registry

registry.register(
    name="bash",
    description="Run a shell command and return its output. Use for system commands, git, package managers, etc.",
    parameters={
        "command": {"type": "string", "description": "The shell command to execute."},
        "timeout": {"type": "integer", "description": "Timeout in seconds. Default 30."},
    },
    handler=tool_bash,
    toolset="general",
)

registry.register(
    name="cmd",
    description="Run a Windows CMD command and return its output. Only available on Windows systems.",
    parameters={
        "command": {"type": "string", "description": "The Windows CMD command to execute."},
        "timeout": {"type": "integer", "description": "Timeout in seconds. Default 30."},
    },
    handler=tool_cmd,
    toolset="general",
)

registry.register(
    name="read_file",
    description="Read the contents of a file under the workspace directory.",
    parameters={
        "file_path": {"type": "string", "description": "Path relative to workspace directory."},
    },
    handler=tool_read_file,
    toolset="file",
)

registry.register(
    name="list_directory",
    description="List files and subdirectories in a directory under workspace.",
    parameters={
        "directory": {"type": "string", "description": "Path relative to workspace directory. Default is root."},
    },
    handler=tool_list_directory,
    toolset="file",
)

registry.register(
    name="get_current_time",
    description="Get the current date and time in UTC.",
    parameters={},
    handler=tool_get_current_time,
    toolset="general",
)

registry.register(
    name="write_file",
    description="Write content to a file. Creates parent directories if needed. Overwrites existing content.",
    parameters={
        "file_path": {"type": "string", "description": "Path to the file (relative to working directory)."},
        "content": {"type": "string", "description": "The content to write."},
    },
    handler=tool_write_file,
    toolset="file",
)

registry.register(
    name="edit_file",
    description="Replace an exact string in a file with a new string. The old_string must appear exactly once in the file.",
    parameters={
        "file_path": {"type": "string", "description": "Path to the file (relative to working directory)."},
        "old_string": {"type": "string", "description": "The exact text to find and replace. Must be unique."},
        "new_string": {"type": "string", "description": "The replacement text."},
    },
    handler=tool_edit_file,
    toolset="file",
)

# 向后兼容的模块级导出
_file_tool_names = {"bash", "cmd", "read_file", "list_directory", "get_current_time", "write_file", "edit_file"}
TOOLS = [t for t in registry.get_tools() if t["name"] in _file_tool_names]
TOOL_HANDLERS: dict[str, Any] = {
    "bash": tool_bash,
    "cmd": tool_cmd,
    "read_file": tool_read_file,
    "list_directory": tool_list_directory,
    "get_current_time": tool_get_current_time,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
}
```

- [ ] **Step 3: Migrate browser_tools.py**

Replace the bottom section (from line 103 `TOOLS = [` to line 148 end) with:

```python
from agentd.tools.registry import registry

registry.register(
    name="web_search",
    description="Search the web and return results. Use for looking up information, news, etc.",
    parameters={
        "query": {"type": "string", "description": "The search query."},
        "num_results": {"type": "integer", "description": "Number of results to return. Default 10."},
    },
    handler=search,
    toolset="browser",
)

registry.register(
    name="get_webpage",
    description="Fetch the content of a webpage given its URL. Use for retrieving information from specific pages.",
    parameters={
        "url": {"type": "string", "description": "The URL of the webpage to fetch."},
    },
    handler=get_webpage,
    toolset="browser",
)

# 向后兼容
_browser_tool_names = {"web_search", "get_webpage"}
TOOLS = [t for t in registry.get_tools() if t["name"] in _browser_tool_names]
TOOL_HANDLERS = {
    "web_search": search,
    "get_webpage": get_webpage,
}
```

- [ ] **Step 4: Migrate skill_tools.py — static description**

Replace the TOOLS list (lines 29-51) and TOOL_HANDLERS (lines 53-55) with registry-based:

```python
from agentd.tools.registry import registry

registry.register(
    name="skill_invoke",
    description=(
        "加载一个已注册的技能模块，获取其完整操作指令。"
        "加载后，你必须严格按照技能指令执行——技能定义的是操作流程，不是参考建议。"
        "可用技能列表见系统提示词中的技能注册表。"
    ),
    parameters={
        "name": {"type": "string", "description": "要加载的技能名称"},
        "args": {"type": "string", "description": "传递给技能的可选参数"},
    },
    handler=tool_skill_invoke,
    toolset="skill",
)

# 向后兼容
TOOLS = [t for t in registry.get_tools() if t["name"] == "skill_invoke"]
TOOL_HANDLERS: dict[str, Any] = {"skill_invoke": tool_skill_invoke}
```

- [ ] **Step 5: Simplify tool_handlers.py**

Replace the entire file with:

```python
"""工具汇总入口 — import 触发各工具模块自注册到 ToolRegistry。"""

# 导入即注册（利用 Python 模块加载副作用）
from agentd.tools import memory_tools   # noqa: F401
from agentd.tools import file_tools     # noqa: F401
from agentd.tools import browser_tools  # noqa: F401
from agentd.tools import skill_tools    # noqa: F401

from agentd.tools.registry import registry


def get_tools():
    return registry.get_tools()


def get_tool_handlers():
    return registry.get_handlers()


# 向后兼容的模块级变量
TOOLS = get_tools()
TOOL_HANDLERS = get_tool_handlers()
```

- [ ] **Step 6: Commit**

```bash
git add agentd/tools/memory_tools.py agentd/tools/file_tools.py agentd/tools/browser_tools.py agentd/tools/skill_tools.py agentd/tools/tool_handlers.py
git commit -m "refactor: migrate all tools to declarative ToolRegistry"
```

archived-with: 2026-06-21-hermes-agent-refactor
---

### Task 4: ContextGuard — Preflight Compression

**Files:**
- Modify: `agentd/context/context.py`

**Interfaces:**
- Consumes: Existing `ContextGuard` class
- Produces: `preflight(system, messages) -> list[dict]` method
- Produces: Reduced `max_retries` from 2 to 1 in `guard_api_call`

- [ ] **Step 1: Add preflight method to ContextGuard**

Add `PREFLIGHT_RATIO` class attribute and `preflight` method to `ContextGuard`. Insert after `estimate_messages_tokens()` (line 84):

```python
class ContextGuard:
    """保护 agent 免受上下文窗口溢出。"""

    PREFLIGHT_RATIO = 0.8  # 80% 阈值触发预飞压缩

    # ... existing __init__, estimate_tokens, estimate_messages_tokens ...

    def preflight(self, system: str, messages: list[dict]) -> list[dict]:
        """预飞检查：估算 token 总量，超阈值主动压缩后返回。

        不超阈值时返回原 messages（零开销）。
        压缩失败时返回原 messages（让反应式重试兜底）。
        """
        total = self.estimate_tokens(system) + self.estimate_messages_tokens(messages)
        if total > self.max_tokens * self.PREFLIGHT_RATIO:
            print_warn(
                f"  [preflight] ~{total:,} tokens (>{self.PREFLIGHT_RATIO*100:.0f}% threshold), "
                f"compacting..."
            )
            try:
                return self.compact_history(messages)
            except Exception as exc:
                print_warn(f"  [preflight] compact failed: {exc}, skipping")
                return messages
        return messages
```

- [ ] **Step 2: Reduce max_retries in guard_api_call and its variants**

In `guard_api_call()` — change `max_retries: int = 2` to `max_retries: int = 1` (line 235).
In `guard_api_call_stream()` — same change (line 290).

- [ ] **Step 3: Commit**

```bash
git add agentd/context/context.py
git commit -m "feat: add preflight compression to ContextGuard, reduce retries"
```

archived-with: 2026-06-21-hermes-agent-refactor
---

### Task 5: AgentRunner — Core Refactor

**Files:**
- Modify: `agentd/agent/runner.py`
- Modify: `agentd/prompt/prompts.py`
- Modify: `agentd/skill/skill.py`

**Interfaces:**
- Consumes: `IterationBudget` (Task 1), `ToolRegistry` (Tasks 2-3), `ContextGuard.preflight` (Task 4)
- Produces: Unified async `run_turn()` with prompt caching, budget loop, preflight, memory-in-user-message

- [ ] **Step 1: Update prompts.py — remove timestamp from system prompt, make memory_context optional**

In `build_system_prompt()`, change Layer 7 to omit current time:

```python
# Layer 7: Runtime Context — without timestamp (moved to user message)
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
sections.append(
    f"## Runtime Context\n\n"
    f"- Agent ID: {agent_id}\n- Model: {MODEL['name']}\n"
    f"- Channel: {channel}\n- Prompt mode: {mode}"
)
```

Also remove the Layer 5 memory_context injection from system prompt — keep the `MEMORY.md` evergreen memory but remove `memory_context` (recalled) from system prompt. Change Layer 5 to:

```python
# Layer 5: Memory — evergreen only (recalled memories moved to user message)
if mode == "full":
    mem_md = bootstrap.get("MEMORY.md", "").strip()
    if mem_md:
        sections.append(f"## Memory\n\n### Evergreen Memory\n\n{mem_md}")
    sections.append(
        "## Memory Instructions\n\n"
        "- Use memory_write to save important user facts and preferences.\n"
        "- Reference remembered facts naturally in conversation.\n"
        "- Use memory_search to recall specific past information."
    )
```

Note: `memory_context` parameter stays in the function signature for backward compat but is no longer used. Keep the parameter with default `""`.

- [ ] **Step 2: Delete build_skill_invoke_tool() from skill.py**

Remove the `build_skill_invoke_tool()` method (lines 88-117) from `SkillsManager`. Keep `get_skill()`, `format_skill_registry()`, `format_prompt_block()`, and all other methods.

- [ ] **Step 3: Rewrite runner.py — unified async entry**

The full new `runner.py`:

```python
# agentd/agent/runner.py
import logging
from datetime import datetime, timezone
from agentd.bootstrap import container as _container
from agentd.context.session import SessionStore
from agentd.context.context import ContextGuard
from agentd.memory.memory import MemoryStore
from agentd.skill.skill import SkillsManager
from agentd.prompt.prompts import build_system_prompt
from agentd.agent.budget import IterationBudget
from config.configs import MAX_TOOL_ITERATIONS

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    Cli 和 Gateway 共用的 LLM 循环核心（统一异步入口）。

    职责：memory recall → build/cache prompt → preflight → LLM call → tool loop → save → return text
    不管：如何获取输入、如何展示/发送输出（由调用方决定）

    调用方持有 messages 和 store，以引用形式传入，runner 直接修改。
    """

    def __init__(self):
        self.container    = _container
        self.guard: ContextGuard  = _container.get("guard")
        self.memory_store: MemoryStore  = _container.get("memory_store")
        self.bootstrap_data: dict       = _container.get("bootstrap_data")
        self.skills_mgr: SkillsManager  = _container.get("skills_mgr")
        self.skill_registry: str        = self.skills_mgr.format_skill_registry()
        self.max_iterations: int        = MAX_TOOL_ITERATIONS

        # System prompt 缓存 — 首次构建，跨轮复用
        self._cached_system_prompt: str | None = None

    # ── 工具调用 ──────────────────────────────────
    def process_tool_call(self, tool_name: str, tool_input: dict) -> str:
        handler = self.container.tools_handlers.get(tool_name)
        if handler is None:
            return f"Error: Unknown tool '{tool_name}'"
        try:
            return handler(**tool_input)
        except TypeError as exc:
            return f"Error: Invalid arguments for {tool_name}: {exc}"
        except Exception as exc:
            return f"Error: {tool_name} failed: {exc}"

    # ── 公共序列化逻辑 ────────────────────────────
    @staticmethod
    def _serialize(response) -> list[dict]:
        result = []
        for block in response.content:
            if hasattr(block, "text"):
                result.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                result.append({
                    "type": "tool_use",
                    "id":    block.id,
                    "name":  block.name,
                    "input": block.input,
                })
        return result

    @staticmethod
    def _extract_text(response) -> str:
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

    @staticmethod
    def _rollback(messages: list[dict]) -> None:
        """出错时回滚到最近的 user 消息"""
        while messages and messages[-1]["role"] != "user":
            messages.pop()
        if messages:
            messages.pop()

    # ── 统一异步入口 ─────────────────────────────
    async def run_turn(
        self,
        user_input: str,
        messages: list[dict],
        store: SessionStore,
        channel: str = "terminal",
    ) -> str:
        """
        返回 assistant 文本回复，出错返回空字符串。

        CLI 端通过 asyncio.run() 调用，Gateway 端直接 await。
        """
        # 1. 记忆召回
        memory_context = self.memory_store._auto_recall(user_input)

        # 2. System prompt 缓存：首次构建，后续复用
        if self._cached_system_prompt is None:
            self._cached_system_prompt = build_system_prompt(
                mode="full",
                bootstrap=self.bootstrap_data,
                skill_registry=self.skill_registry,
                channel=channel,
            )

        # 3. 记忆上下文 + 时间戳注入 user message
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        parts = [f"[系统时间: {now}]"]
        if memory_context:
            parts.append(f"[记忆上下文]\n{memory_context}")
        parts.append(f"[用户消息]\n{user_input}")
        user_content = "\n\n".join(parts)

        messages.append({"role": "user", "content": user_content})
        store.save_turn("user", user_input)

        # 4. 工具循环（含迭代预算 + 预飞压缩）
        budget = IterationBudget(self.max_iterations)
        last_response = None

        while budget.remaining > 0:
            budget.consume()

            # 预飞压缩：主动检查 token，超阈值先压缩
            messages = self.guard.preflight(self._cached_system_prompt, messages)

            try:
                response = await self.guard.async_guard_api_call(
                    system=self._cached_system_prompt,
                    messages=messages,
                    tools=self.container.tools,
                )
                last_response = response
            except Exception as exc:
                logger.exception("[Runner] LLM 调用异常: %s", exc)
                self._rollback(messages)
                return ""

            messages.append({"role": "assistant", "content": response.content})
            store.save_turn("assistant", self._serialize(response))

            if response.stop_reason == "end_turn":
                return self._extract_text(response)

            elif response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = self.process_tool_call(block.name, block.input)
                    store.save_tool_result(block.id, block.name, block.input, result)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })
                messages.append({"role": "user", "content": tool_results})

            else:
                logger.info("[Runner] stop_reason=%s", response.stop_reason)
                return self._extract_text(response)

        # 预算耗尽 — 返回最后一条 assistant 文本
        if last_response:
            return self._extract_text(last_response)
        return "已达到工具调用上限，对话终止。"
```

- [ ] **Step 4: Commit**

```bash
git add agentd/agent/runner.py agentd/prompt/prompts.py agentd/skill/skill.py
git commit -m "refactor: unified async runner with prompt cache, budget, preflight"
```

archived-with: 2026-06-21-hermes-agent-refactor
---

### Task 6: Entry Point Adaptation

**Files:**
- Modify: `cli/cli.py`
- Modify: `gateway/gateway.py`

**Interfaces:**
- Consumes: `AgentRunner.run_turn()` (now async)
- Produces: CLI uses `asyncio.run()`, Gateway uses updated method name

- [ ] **Step 1: Adapt cli.py — use asyncio.run()**

In `cli/cli.py`:
1. Add `import asyncio` at top
2. Change `handle_user_input()` line 68:

```python
# cli/cli.py — add at top
import asyncio

# In handle_user_input():
def handle_user_input(self, user_input: str):
    if user_input.startswith("/") and self.handle_repl_command(user_input):
        return
    reply = asyncio.run(
        self.runner.run_turn(
            user_input=user_input,
            messages=self.messages,
            store=self.store,
            channel="terminal",
        )
    )
    if reply:
        print_assistant(reply)
```

Also update the `/prompt` command to reflect new prompt structure:

```python
elif cmd == "/prompt":
    print_section("完整系统提示词")
    prompt = build_system_prompt(
        mode="full", bootstrap=self.runner.bootstrap_data,
        skill_registry=self.runner.skill_registry,
        channel="terminal",
    )
    # ... rest unchanged
```

- [ ] **Step 2: Adapt gateway.py — method name change**

In `gateway.py` line 113, change `async_run_turn` to `run_turn`:

```python
async with self._get_user_lock(msg.user_id):
    reply = await self.runner.run_turn(
        user_input=msg.content,
        messages=messages,
        store=store,
        channel=platform.channel,
    )
```

- [ ] **Step 3: Commit**

```bash
git add cli/cli.py gateway/gateway.py
git commit -m "refactor: adapt CLI/Gateway to unified async run_turn"
```

archived-with: 2026-06-21-hermes-agent-refactor
---

### Task 7: Verification

**Files:**
- (no code changes — verification only)

- [ ] **Step 1: Verify CLI starts correctly**

```bash
cd c:/self/work/todo/ultimate_try && timeout 5 python ultimate.py chat 2>&1 || true
```
Expected: Prints "ultimate agent 启动成功", tool list includes skill_invoke.

- [ ] **Step 2: Verify tool registry integrity**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
from agentd.tools.registry import registry
tools = registry.get_tools()
names = {t['name'] for t in tools}
expected = {'bash', 'cmd', 'read_file', 'list_directory', 'get_current_time', 'write_file', 'edit_file', 'memory_write', 'memory_search', 'web_search', 'get_webpage', 'skill_invoke'}
print(f'Tools: {names}')
assert names == expected, f'Missing: {expected - names}, Extra: {names - expected}'
print('OK: All tools registered')
"
```
Expected: `OK: All tools registered`

- [ ] **Step 3: Verify tool handler dispatch**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
from agentd.tools.registry import registry
handlers = registry.get_handlers()
for name in ['bash', 'memory_write', 'skill_invoke']:
    assert name in handlers, f'Missing handler: {name}'
    assert callable(handlers[name]), f'Handler not callable: {name}'
print('OK: All handlers callable')
"
```
Expected: `OK: All handlers callable`

- [ ] **Step 4: Verify IterationBudget**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
from agentd.agent.budget import IterationBudget
b = IterationBudget(3)
assert b.remaining == 3
assert b.consume() == True
assert b.remaining == 2
b.consume()
b.consume()
assert b.remaining == 0
assert b.consume() == False
print('OK: Budget works')
"
```
Expected: `OK: Budget works`

- [ ] **Step 5: Verify preflight does not crash on normal input**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
from agentd.context.context import ContextGuard
g = ContextGuard()
msgs = [{'role': 'user', 'content': 'hello'}]
result = g.preflight('system prompt', msgs)
assert result == msgs, 'Preflight should return unchanged messages for small input'
print('OK: Preflight passes through small input')
"
```
Expected: `OK: Preflight passes through small input`

- [ ] **Step 6: Update tasks.md checkboxes**

Mark all tasks as complete in `openspec/changes/hermes-agent-refactor/tasks.md`.

- [ ] **Step 7: Commit**

```bash
git add openspec/changes/hermes-agent-refactor/tasks.md
git commit -m "chore: mark all tasks complete after verification"
```
