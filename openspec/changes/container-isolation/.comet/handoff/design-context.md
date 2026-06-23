# Comet Design Handoff

- Change: container-isolation
- Phase: design
- Mode: compact
- Context hash: 6d909abd798282264ec0fa27dc1560a5d469c3004ae183c7b706954a670a5315

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/container-isolation/proposal.md

- Source: openspec/changes/container-isolation/proposal.md
- Lines: 1-31
- SHA256: f84ec3f2011f17ce97bfaddd28be60adff34d954aed260738830a85c4ed894d7

```md
## Why

当前 `container = Container()` 是模块级全局单例。当多个 CLI 实例或 CLI + Gateway 同时运行时，它们共享同一个 ContextGuard、ProviderRouter、MemoryStore、SkillsManager 实例，导致状态互相污染（如 router.reset() 互相干扰、guard 上下文混淆）。需要将容器改为 per-session 实例化，每个 AgentRunner 拥有独立的依赖图。

## What Changes

- **BREAKING**: 移除模块级全局 `container` 单例；`agentd.bootstrap.container` 不再导出预实例化的 `container`
- AgentRunner 构造时创建自己的 `Container` 实例（或直接实例化依赖）
- 工具函数 (`memory_tools.py`, `skill_tools.py`) 通过 `contextvars.ContextVar` 获取当前容器，而非导入全局单例
- Cli 通过 AgentRunner 访问依赖，不再直接访问 `runner.container`
- Container 类保留但改为支持 per-session 参数（`session_id`）

## Capabilities

### New Capabilities

- `per-session-container`: 每个 AgentRunner 实例拥有独立的依赖注入容器，通过 `contextvars` 实现工具函数的隐式依赖传递

### Modified Capabilities

<!-- None — 纯内部架构重构，不改变外部行为 -->

## Impact

- `agentd/bootstrap/container.py`: Container 类保留，移除全局 `container` 单例
- `agentd/bootstrap/__init__.py`: 移除 `container` 导出
- `agentd/agent/runner.py`: AgentRunner.__init__ 创建自己的依赖
- `agentd/tools/memory_tools.py`: 通过 contextvar 获取 MemoryStore
- `agentd/tools/skill_tools.py`: 通过 contextvar 获取 SkillsManager
- `cli/cli.py`: 适配新的 AgentRunner 接口
- 现有 56 个测试需保持通过，新增 per-session 隔离测试
```

## openspec/changes/container-isolation/design.md

- Source: openspec/changes/container-isolation/design.md
- Lines: 1-50
- SHA256: 91419baeaf3c37324dc128944e78cf994e99c3d39a8c7cdae39d697c9f77a104

```md
## 架构决策

**方案**: AgentRunner 构造时创建自己的 `Container` 实例；通过 `contextvars.ContextVar` 让工具函数能访问"当前"容器。

```
AgentRunner(session_id="abc")        AgentRunner(session_id="xyz")
  │                                    │
  └─ Container()                       └─ Container()
       │                                    │
       ├─ ContextGuard(...)                  ├─ ContextGuard(...)
       ├─ MemoryStore(WORKSPACE_DIR)         ├─ MemoryStore(WORKSPACE_DIR)
       ├─ SkillsManager(WORKSPACE_DIR)       ├─ SkillsManager(WORKSPACE_DIR)
       └─ ProviderRouter(...)                └─ ProviderRouter(...)
```

**备选方案（不采用）**:
- 线程局部 (`threading.local`): 不适用于 asyncio 并发模型，多个协程共享同一线程
- AgentRunner 直接 `new` 依赖（无 Container）: 会丢失依赖注册/查找的灵活性，工具函数适配成本更高

## ContextVar 机制

```python
# agentd/bootstrap/context.py (新增)
import contextvars

_current_container: contextvars.ContextVar = contextvars.ContextVar("current_container")

def set_current_container(c): ...
def get_current_container(): ...
```

工具函数从 `container.get("memory_store")` 改为 `get_current_container().get("memory_store")`。

## 变更文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `agentd/bootstrap/context.py` | **新建** | ContextVar 存储/获取当前容器 |
| `agentd/bootstrap/container.py` | 修改 | Container 支持 session_id，移除全局单例 |
| `agentd/bootstrap/__init__.py` | 修改 | 移除 `container` 导出，新增 contextvar helpers |
| `agentd/agent/runner.py` | 修改 | __init__ 创建 Container，设置 contextvar |
| `agentd/tools/memory_tools.py` | 修改 | 通过 contextvar 获取 MemoryStore |
| `agentd/tools/skill_tools.py` | 修改 | 通过 contextvar 获取 SkillsManager |
| `cli/cli.py` | 修改 | 适配新 AgentRunner 接口（去掉 container 直接访问） |
| `tests/test_container_isolation.py` | **新建** | per-session 隔离测试 |

## 测试策略

- **单元测试**: 两个 AgentRunner 实例的 container 互相独立，contextvar 正确传播
- **回归测试**: 现有 56 个测试全部保持通过
```

## openspec/changes/container-isolation/tasks.md

- Source: openspec/changes/container-isolation/tasks.md
- Lines: 1-28
- SHA256: ca9a9a2cf2fe1d6057ca3fb8b8e8a3f21a8ea29c96ddbd5d4c0b50a3b5cd5b98

```md
## Tasks

### Task 1: 新建 ContextVar 模块 (`agentd/bootstrap/context.py`)

- [ ] 创建 `agentd/bootstrap/context.py` — `_current_container` ContextVar + `set_current_container()` / `get_current_container()` 函数

### Task 2: Container 改造 + 移除全局单例

- [ ] `agentd/bootstrap/container.py`: 移除 `container = Container()` 全局单例；Container `__init__` 支持可选 `session_id` 参数
- [ ] `agentd/bootstrap/__init__.py`: 移除 `container` 导出，新增 `set_current_container` / `get_current_container` 导出

### Task 3: AgentRunner per-session Container

- [ ] `agentd/agent/runner.py`: AgentRunner `__init__` 创建自己的 Container，设置 contextvar；通过 `self.container` 访问依赖（保持内部使用模式不变）

### Task 4: 工具函数适配 ContextVar

- [ ] `agentd/tools/memory_tools.py`: 通过 `get_current_container()` 替代 `from agentd.bootstrap import container`
- [ ] `agentd/tools/skill_tools.py`: 通过 `get_current_container()` 替代 `from agentd.bootstrap import container`

### Task 5: CLI 适配

- [ ] `cli/cli.py`: 去掉对 `self.runner.container` 的直接访问，改为通过 AgentRunner 暴露的属性访问依赖

### Task 6: 测试 + 回归

- [ ] 新建 `tests/test_container_isolation.py` — 验证两个 AgentRunner 实例的 container 互相独立
- [ ] 运行全量测试：`python -m pytest tests/ -x -q` — 确认 56 个现有测试 + 新测试全部通过
```

