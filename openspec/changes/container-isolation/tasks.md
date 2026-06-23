## Tasks

### Task 1: 新建 ContextVar 模块 (`agentd/bootstrap/context.py`)

- [x] 创建 `agentd/bootstrap/context.py` — `_current_container` ContextVar + `set_current_container()` / `get_current_container()` 函数

### Task 2: Container 改造 + 移除全局单例

- [x] `agentd/bootstrap/container.py`: 移除 `container = Container()` 全局单例；Container `__init__` 支持可选 `session_id` 参数
- [x] `agentd/bootstrap/__init__.py`: 移除 `container` 导出，新增 `set_current_container` / `get_current_container` 导出

### Task 3: AgentRunner per-session Container

- [x] `agentd/agent/runner.py`: AgentRunner `__init__` 创建自己的 Container，设置 contextvar；通过 `self.container` 访问依赖（保持内部使用模式不变）

### Task 4: 工具函数适配 ContextVar

- [x] `agentd/tools/memory_tools.py`: 通过 `get_current_container()` 替代 `from agentd.bootstrap import container`
- [x] `agentd/tools/skill_tools.py`: 通过 `get_current_container()` 替代 `from agentd.bootstrap import container`

### Task 5: CLI 适配

- [x] `cli/cli.py`: 去掉对 `self.runner.container` 的直接访问，改为通过 AgentRunner 暴露的属性访问依赖

### Task 6: 测试 + 回归

- [x] 新建 `tests/test_container_isolation.py` — 验证两个 AgentRunner 实例的 container 互相独立
- [x] 运行全量测试：`python -m pytest tests/ -x -q` — 确认 56 个现有测试 + 新测试全部通过（68 passed）
