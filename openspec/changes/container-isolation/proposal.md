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
