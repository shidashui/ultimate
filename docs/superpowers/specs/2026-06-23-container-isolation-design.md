---
comet_change: container-isolation
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-23-container-isolation
status: final
---

# Per-Session Container Isolation — 技术设计

## 架构

```
AgentRunner(session_id="abc")              AgentRunner(session_id="xyz")
  │ run_turn()                              │ run_turn()
  │   set_current_container(self.container) │   set_current_container(self.container)
  │   ▼                                     │   ▼
  │ ┌─────────────────────────────────┐     │ ┌─────────────────────────────────┐
  │ │ Container("abc")                │     │ │ Container("xyz")                │
  │ │  ├─ ContextGuard(router)        │     │ │  ├─ ContextGuard(router)        │
  │ │  ├─ MemoryStore(WORKSPACE_DIR)  │     │ │  ├─ MemoryStore(WORKSPACE_DIR)  │
  │ │  ├─ SkillsManager(WORKSPACE_DIR)│     │ │  ├─ SkillsManager(WORKSPACE_DIR)│
  │ │  ├─ SessionDB(...)              │     │ │  ├─ SessionDB(...)              │
  │ │  └─ ProviderRouter(providers)   │     │ │  └─ ProviderRouter(providers)   │
  │ └──────────┬──────────────────────┘     │ └──────────┬──────────────────────┘
  │            │                            │            │
  │   process_tool_call()                   │   process_tool_call()
  │     → tool_memory_write()               │     → tool_memory_write()
  │       → get_current_container()          │       → get_current_container()
  │         .get("memory_store")             │         .get("memory_store")
```

### 分层职责

| 层 | 模块 | 职责 |
|----|------|------|
| 工厂 | `agentd/bootstrap/container.py` | Container 类，按 session_id 实例化依赖图 |
| 传递 | `agentd/bootstrap/context.py` | ContextVar 存储/获取当前容器 |
| 入口 | `agentd/agent/runner.py` | run_turn() 设置/清理 ContextVar |
| 消费 | `agentd/tools/*.py` | 通过 `get_current_container()` 获取依赖 |
| 暴露 | `AgentRunner` 属性 | `tools_handlers`, `session_db` 等 CLI 直接访问 |

## 组件

### ContextVar 模块 (`agentd/bootstrap/context.py`)

```python
import contextvars

_current_container: contextvars.ContextVar = contextvars.ContextVar(
    "current_container", default=None
)

def set_current_container(container) -> None:
    _current_container.set(container)

def get_current_container():
    c = _current_container.get()
    if c is None:
        raise RuntimeError(
            "No container set — must be called within AgentRunner.run_turn()"
        )
    return c
```

### Container 改造 (`agentd/bootstrap/container.py`)

- **移除**: 模块级 `container = Container()` 全局单例（第 54 行）
- `Container.__init__(self, session_id: str | None = None)`: 增加可选 session_id 参数
- 其余初始化逻辑（BootstrapLoader、SkillsManager、MemoryStore、ProviderRouter 创建）不变

### AgentRunner 改造 (`agentd/agent/runner.py`)

```python
class AgentRunner:
    def __init__(self, session_id=None):
        self.container = Container(session_id=session_id)
        self.guard = self.container.get("guard")
        self.memory_store = self.container.get("memory_store")
        # ... 其余 .get() 不变
        self._cached_system_prompt = None

    async def run_turn(self, ...):
        set_current_container(self.container)
        try:
            # ... 现有逻辑
        finally:
            set_current_container(None)
```

### 工具函数适配

```python
# memory_tools.py
def tool_memory_write(content, category="general"):
    from agentd.bootstrap import get_current_container
    memory_store = get_current_container().get("memory_store")
    ...

# skill_tools.py
def tool_skill_invoke(name, args=""):
    from agentd.bootstrap import get_current_container
    skills_mgr = get_current_container().get("skills_mgr")
    ...
```

### CLI 适配 (`cli/cli.py`)

AgentRunner 暴露便捷属性，CLI 不再越级访问 `runner.container`：

| CLI 当前访问 | 改为 |
|-------------|------|
| `self.runner.container.get("session_db")` | `self.runner.session_db` |
| `self.runner.container.tools_handlers` | `self.runner.tools_handlers` |
| `self.runner.memory_store` | 已有，不变 |
| `self.runner.skills_mgr` | 已有，不变 |
| `self.runner.guard` | 已有，不变 |
| `self.runner.bootstrap_data` | 已有，不变 |

## 错误处理

- ContextVar 未设置时 `get_current_container()` 抛出 `RuntimeError`，明确指示调用链错误
- `run_turn()` 用 `try/finally` 确保 ContextVar 清理，防止泄漏到其他协程
- `set_current_container(None)` 是安全的清理操作（非强制要求但防御性编程）

## 测试策略

### 单元测试

| 测试 | 内容 |
|------|------|
| ContextVar 设置/获取 | `set_current_container()` → `get_current_container()` 往返 |
| ContextVar 未设置抛错 | 未调用 `set` 时 `get` → `RuntimeError` |
| 两个 Container 隔离 | 两个 AgentRunner 实例的 container 互相独立 |
| ContextVar 清理 | `finally` 块正确清理 |

### 回归

- 现有 56 个测试全部保持通过
- 测试类自己设置 ContextVar 或 mock 工具函数

## 风险

| 风险 | 缓解 |
|------|------|
| 工具函数在 run_turn() 外被调用 | `get_current_container()` 抛明确 RuntimeError |
| 异步协程间 ContextVar 泄漏 | `finally` 清理 + ContextVar 原生 asyncio 隔离 |
| 已有外部代码依赖 `from agentd.bootstrap import container` | 逐个修改（4 处已知），编译/导入检查兜底 |
