---
change: container-isolation
design-doc: docs/superpowers/specs/2026-06-23-container-isolation-design.md
base-ref: d2199f118159cd179ba965d4df9784b8bbc934ad
---

# Per-Session Container Isolation 实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将全局单例 `container = Container()` 改为 per-session 实例化，每个 AgentRunner 持有独立 Container，通过 ContextVar 传递依赖给工具函数。

**Architecture:** AgentRunner 构造时创建 Container；run_turn() 入口设置 ContextVar，工具函数通过 `get_current_container()` 获取当前容器的依赖。try/finally 确保 ContextVar 清理。

**Tech Stack:** Python 3.12+ `contextvars` 标准库，零外部依赖

## Global Constraints

- 纯 Python 标准库，零外部依赖
- AgentRunner.__init__ 接受 `session_id: str | None = None` 参数
- run_turn 用 try/finally 确保 ContextVar 清理
- `get_current_container()` 未设置时抛 RuntimeError
- 现有 56 个测试保持通过
- 每次提交格式：`feat: <简述>`，Co-Authored-By: Claude <noreply@anthropic.com>

---

### Task 1: 新建 ContextVar 模块

**Files:**
- Create: `agentd/bootstrap/context.py`

**Interfaces:**
- Produces: `set_current_container(container: Container) -> None`, `get_current_container() -> Container`

- [ ] **Step 1: 创建 agentd/bootstrap/context.py**

```python
"""Per-session container access via contextvars.

Each AgentRunner.run_turn() sets the current container at entry
and clears it on exit. Tool functions call get_current_container()
to reach their dependencies without importing a global singleton.
"""
from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentd.bootstrap.container import Container

_current_container: contextvars.ContextVar[Container | None] = (
    contextvars.ContextVar("current_container", default=None)
)


def set_current_container(container: Container | None) -> None:
    """Set the container for the current async context."""
    _current_container.set(container)


def get_current_container() -> Container:
    """Return the current session's container.

    Raises RuntimeError if called outside AgentRunner.run_turn().
    """
    c = _current_container.get()
    if c is None:
        raise RuntimeError(
            "No container set — must be called within AgentRunner.run_turn()"
        )
    return c
```

- [ ] **Step 2: 验证模块可导入**

Run: `cd c:/self/work/todo/ultimate_try && python -c "from agentd.bootstrap.context import set_current_container, get_current_container; print('context module OK')"`
Expected: `context module OK`

- [ ] **Step 3: 提交**

```bash
git add agentd/bootstrap/context.py
git commit -m "feat: add ContextVar-based container access module

agentd/bootstrap/context.py provides set_current_container() and
get_current_container() for per-session container isolation.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Container 改造 — 移除全局单例

**Files:**
- Modify: `agentd/bootstrap/container.py:53-54` (移除 `container = Container()`)

**Interfaces:**
- Consumes: (none)
- Produces: `Container.__init__(self, session_id: str | None = None)` — session_id 为可选参数

- [ ] **Step 1: 移除全局单例 + 添加 session_id 参数**

Edit `agentd/bootstrap/container.py` — 两处改动：

改动 A: `__init__` 签名增加 `session_id` 参数

```python
# line 9-11, 改为:
class Container:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id
        self.tools = []
        self.tools_handlers = {}
        self.services = {}
        self.initialize()
```

改动 B: 删除文件末尾的全局单例

```python
# 删除第 53-54 行:
# ✅ 全局唯一实例（但不是全局变量乱飞）
container = Container()
```

- [ ] **Step 2: 验证 Container 可独立实例化**

Run: `cd c:/self/work/todo/ultimate_try && python -c "from agentd.bootstrap.container import Container; c1 = Container('a'); c2 = Container('b'); assert c1.session_id == 'a'; assert c2.session_id == 'b'; print('OK: two independent containers')"`
Expected: `OK: two independent containers`

- [ ] **Step 3: 提交**

```bash
git add agentd/bootstrap/container.py
git commit -m "feat: remove global container singleton, add session_id

Container is now per-session instantiable. session_id is optional.
Removed module-level 'container = Container()' singleton.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 更新 bootstrap __init__.py 导出

**Files:**
- Modify: `agentd/bootstrap/__init__.py:1` (移除 `container` 导出，新增 contextvar helpers)

**Interfaces:**
- Consumes: `agentd/bootstrap/context.py` (Task 1), `agentd/bootstrap/container.py` (Task 2)
- Produces: `set_current_container`, `get_current_container` 从 `agentd.bootstrap` 可导入

- [ ] **Step 1: 修改 __init__.py**

```python
from agentd.bootstrap.container import Container
from agentd.bootstrap.loader import BootstrapLoader
from agentd.bootstrap.context import set_current_container, get_current_container
```

- [ ] **Step 2: 验证导入**

Run: `cd c:/self/work/todo/ultimate_try && python -c "from agentd.bootstrap import Container, BootstrapLoader, set_current_container, get_current_container; print('bootstrap exports OK')"`
Expected: `bootstrap exports OK`

- [ ] **Step 3: 提交**

```bash
git add agentd/bootstrap/__init__.py
git commit -m "feat: update bootstrap exports for per-session container

Replace 'container' singleton export with set_current_container and
get_current_container contextvar helpers. Container class still exported.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: AgentRunner per-session Container

**Files:**
- Modify: `agentd/agent/runner.py:4,27-37,82-97` (导入、__init__、run_turn)

**Interfaces:**
- Consumes: `Container(session_id)` from Task 2, `set_current_container`/`get_current_container` from Task 3
- Produces: `AgentRunner.__init__(self, session_id=None)` — 创建自己的 Container；`run_turn` 设置/清理 ContextVar

- [ ] **Step 1: 修改导入和 __init__**

改动 A: 导入（第 4 行）

```python
# 旧:
from agentd.bootstrap import container as _container

# 新:
from agentd.bootstrap import Container, set_current_container
```

改动 B: `__init__`（第 27-34 行）

```python
def __init__(self, session_id: str | None = None):
    self.container = Container(session_id=session_id)
    self.guard: ContextGuard  = self.container.get("guard")
    self.memory_store: MemoryStore  = self.container.get("memory_store")
    self.bootstrap_data: dict       = self.container.get("bootstrap_data")
    self.skills_mgr: SkillsManager  = self.container.get("skills_mgr")
    self.skill_registry: str        = self.skills_mgr.format_skill_registry()
    self.max_iterations: int        = MAX_TOOL_ITERATIONS

    # System prompt 缓存 — 首次构建，跨轮复用
    self._cached_system_prompt: str | None = None
```

- [ ] **Step 2: 修改 run_turn — 设置/清理 ContextVar**

改动 C: `run_turn` 方法体（在现有 `provider_router.reset()` 之前加，在方法末尾加 finally）

```python
async def run_turn(
    self,
    user_input: str,
    messages: list[dict],
    store: SessionStore,
    channel: str = "terminal",
) -> str:
    set_current_container(self.container)
    try:
        # 0. 重置 provider 到主（每 turn 重新开始）
        provider_router = self.container.get("provider_router")
        if provider_router:
            provider_router.reset()

        # ... 现有逻辑 (1-4 步) 保持不变 ...

        # 4. 工具循环... 现有代码整个 while 循环放在 try 块内
    finally:
        set_current_container(None)
```

完整修改：将现有 `run_turn` 的方法体（从 `provider_router.reset()` 到 `return` 语句）全部缩进到 `try:` 块内，外层加 `set_current_container` / `finally`。

具体操作：
- 在 `provider_router = self.container.get("provider_router")` 之前插入 `set_current_container(self.container)` + `try:`
- 在方法的最后一个 `return` 之后、方法结束前插入 `finally: set_current_container(None)`

- [ ] **Step 3: 验证 AgentRunner 可实例化**

Run: `cd c:/self/work/todo/ultimate_try && python -c "from agentd.agent.runner import AgentRunner; r = AgentRunner('test'); print(f'session_id={r.container.session_id}'); print(f'guard={type(r.guard).__name__}'); print('AgentRunner OK')"`
Expected: `session_id=test`, `guard=ContextGuard`, `AgentRunner OK`

- [ ] **Step 4: 验证 ContextVar 正确设置**

Run: `cd c:/self/work/todo/ultimate_try && python -c "from agentd.bootstrap.context import get_current_container; print(get_current_container())"`
Expected: `RuntimeError: No container set — must be called within AgentRunner.run_turn()`

- [ ] **Step 5: 提交**

```bash
git add agentd/agent/runner.py
git commit -m "feat: per-session Container in AgentRunner

AgentRunner now creates its own Container instance instead of
importing a global singleton. run_turn() sets/clears ContextVar.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 工具函数适配 ContextVar

**Files:**
- Modify: `agentd/tools/memory_tools.py:11,19` (延迟导入改为 ContextVar)
- Modify: `agentd/tools/skill_tools.py:7` (延迟导入改为 ContextVar)

**Interfaces:**
- Consumes: `get_current_container` from Task 3
- Produces: 工具函数签名不变，内部通过 `get_current_container()` 获取依赖

- [ ] **Step 1: 修改 memory_tools.py**

```python
# tool_memory_write (line 10-15):
def tool_memory_write(content: str, category: str = "general") -> str:
    from agentd.bootstrap import get_current_container

    print_tool("memory_write", f"[{category}] {content[:60]}...")
    memory_store = get_current_container().get("memory_store")
    return memory_store.write_memory(content, category)


# tool_memory_search (line 18-26):
def tool_memory_search(query: str, top_k: int = 5) -> str:
    from agentd.bootstrap import get_current_container

    print_tool("memory_search", query)
    memory_store = get_current_container().get("memory_store")
    results = memory_store.hybrid_search(query, top_k)
    if not results:
        return "No relevant memories found."
    return "\n".join(f"[{r['path']}] (score: {r['score']}) {r['snippet']}" for r in results)
```

- [ ] **Step 2: 修改 skill_tools.py**

```python
# tool_skill_invoke (line 5-22):
def tool_skill_invoke(name: str, args: str = "") -> str:
    """按需加载指定技能模块，返回完整操作指令正文。"""
    from agentd.bootstrap import get_current_container

    print_tool("skill_invoke", name)
    skills_mgr = get_current_container().get("skills_mgr")
    # ... 其余逻辑不变
```

- [ ] **Step 3: 验证工具函数可导入**

Run: `cd c:/self/work/todo/ultimate_try && python -c "from agentd.tools.memory_tools import tool_memory_write, tool_memory_search; from agentd.tools.skill_tools import tool_skill_invoke; print('tool functions OK')"`
Expected: `tool functions OK`

- [ ] **Step 4: 提交**

```bash
git add agentd/tools/memory_tools.py agentd/tools/skill_tools.py
git commit -m "feat: adapt tool functions to ContextVar container access

memory_tools.py and skill_tools.py now use get_current_container()
instead of importing the global container singleton.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: CLI 适配

**Files:**
- Modify: `agentd/agent/runner.py` (新增便捷属性)
- Modify: `cli/cli.py:19-22,30,51,55-58` (去掉越级访问)

**Interfaces:**
- Consumes: AgentRunner from Task 4
- Produces: `AgentRunner.tools_handlers`, `AgentRunner.session_db` 等属性

- [ ] **Step 1: AgentRunner 新增便捷属性**

在 `agentd/agent/runner.py` 的 `AgentRunner` 类中添加两个 property：

```python
@property
def tools_handlers(self) -> dict:
    return self.container.tools_handlers

@property
def session_db(self):
    return self.container.get("session_db")
```

- [ ] **Step 2: 修改 cli/cli.py**

改动 A: `Cli.__init__` (第 19-23 行) — `runner.container` → `runner`

```python
def __init__(self):
    self.store = SessionStore(base_dir=WORKSPACE_DIR, agent_id="zero")
    self.messages: list[dict] = []
    self.runner = AgentRunner()
    # 注入 SessionDB 到 SessionStore（FTS5 全文搜索）
    session_db = self.runner.session_db
    if session_db:
        self.store.session_db = session_db
```

改动 B: `init_run` (第 55 行) — `self.runner.container.tools_handlers.keys()` → `self.runner.tools_handlers.keys()`

```python
f"[primary]工具列表:[/primary] {', '.join(self.runner.tools_handlers.keys())}",
```

改动 C: `init_run` (第 57-58 行) — `self.runner.memory_store` 等属性本身已存在，无需修改（第 30 行 `self.runner.skills_mgr.skills` 已可用）

- [ ] **Step 3: 验证 CLI 初始化**

Run: `cd c:/self/work/todo/ultimate_try && python -c "from cli.cli import Cli; c = Cli(); print(f'tools: {len(c.runner.tools_handlers)}'); print('CLI init OK')"`
Expected: `tools: 12` (or current tool count), `CLI init OK`

- [ ] **Step 4: 提交**

```bash
git add agentd/agent/runner.py cli/cli.py
git commit -m "feat: CLI uses AgentRunner properties, no container escape

AgentRunner exposes tools_handlers and session_db properties.
CLI no longer accesses runner.container directly.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 测试 + 回归

**Files:**
- Create: `tests/test_container_isolation.py`

**Interfaces:**
- Consumes: All previous tasks
- Produces: 测试覆盖 per-session 隔离、ContextVar 设置/清理/错误

- [ ] **Step 1: 编写隔离测试**

```python
"""Tests for per-session container isolation."""
import pytest
from agentd.bootstrap import Container, set_current_container, get_current_container
from agentd.agent.runner import AgentRunner


class TestContextVar:
    """ContextVar set/get/clear behavior."""

    def test_set_and_get(self):
        c = Container("test")
        set_current_container(c)
        try:
            assert get_current_container() is c
            assert get_current_container().session_id == "test"
        finally:
            set_current_container(None)

    def test_get_without_set_raises(self):
        # 确保没有遗留的 contextvar
        set_current_container(None)
        with pytest.raises(RuntimeError, match="No container set"):
            get_current_container()

    def test_set_none_then_get_raises(self):
        set_current_container(None)
        with pytest.raises(RuntimeError, match="No container set"):
            get_current_container()


class TestContainerIsolation:
    """Two AgentRunners have independent containers."""

    def test_independent_containers(self):
        r1 = AgentRunner("session-a")
        r2 = AgentRunner("session-b")

        # 不同的 container 实例
        assert r1.container is not r2.container

        # session_id 独立
        assert r1.container.session_id == "session-a"
        assert r2.container.session_id == "session-b"

    def test_independent_services(self):
        r1 = AgentRunner("a")
        r2 = AgentRunner("b")

        # 每个 runner 有自己的 guard、memory_store 等
        assert r1.guard is not r2.guard
        assert r1.memory_store is not r2.memory_store
        assert r1.skills_mgr is not r2.skills_mgr

    def test_guard_has_own_router(self):
        r1 = AgentRunner("a")
        r2 = AgentRunner("b")

        # ProviderRouter 也是独立的
        router1 = r1.container.get("provider_router")
        router2 = r2.container.get("provider_router")
        assert router1 is not router2


class TestContextVarInRunTurn:
    """ContextVar is set during run_turn and cleared after."""

    @pytest.mark.asyncio
    async def test_contextvar_cleared_after_run_turn(self):
        r = AgentRunner("test")
        set_current_container(None)  # 确保初始状态

        # 模拟最小调用（会失败因为没有真正的 LLM，但 ContextVar 应该清理）
        try:
            await r.run_turn(
                user_input="hi",
                messages=[],
                store=None,  # 会触发 AttributeError，但 finally 应清理
                channel="terminal",
            )
        except Exception:
            pass

        # ContextVar 应该已清理
        with pytest.raises(RuntimeError, match="No container set"):
            get_current_container()
```

- [ ] **Step 2: 运行新测试**

Run: `cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_container_isolation.py -v`
Expected: 4-5 tests PASS

- [ ] **Step 3: 运行全量回归测试**

Run: `cd c:/self/work/todo/ultimate_try && python -m pytest tests/ -x -q --tb=short`
Expected: All tests pass (56 existing + new)

- [ ] **Step 4: 勾选 tasks.md**

将所有 `- [ ]` 改为 `- [x]`。

- [ ] **Step 5: 提交**

```bash
git add tests/test_container_isolation.py openspec/changes/container-isolation/tasks.md
git commit -m "feat: add container isolation tests + mark tasks complete

tests/test_container_isolation.py covers ContextVar lifecycle,
container independence, and tear-down. All existing 56 tests pass.

Co-Authored-By: Claude <noreply@anthropic.com>"
```
