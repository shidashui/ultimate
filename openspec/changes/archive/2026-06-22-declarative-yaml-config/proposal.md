## Why

当前配置系统存在三个痛点：(1) `config.json` 明文存储 API key，存在安全风险且无法通过环境变量注入；(2) `config/configs.py` 将运行时参数（`CONTEXT_SAFE_LIMIT`、`MAX_TOOL_ITERATIONS`）硬编码为 Python 常量，运行时不可改；(3) 单一 model 配置不支持多 provider 切换，`provider` 字段存在但未被代码用于分发。用户换模型需手动编辑 JSON 文件。

## What Changes

- **BREAKING**: 废弃 `config.json`，迁移到 `config.yaml` 声明式配置
- 新增 `model.providers` 列表支持多 provider 声明，`model.default` 选择当前使用的 provider
- API key 通过 `api_key_env` 环境变量注入，不再明文存储
- `toolsets` 段集中管理启用的工具集
- `agent` 段统一管理运行时参数（`max_iterations`、`context_safe_limit`），替代硬编码 Python 常量
- `config/configs.py` 重构为 YAML 加载器，移除硬编码常量
- 提供 `config.example.yaml` 作为新用户模板

## Capabilities

### New Capabilities
- `yaml-config`: 声明式 YAML 配置文件格式与加载逻辑，包含 model（多 provider + 环境变量注入）、toolsets（工具集启用/禁用）、agent（运行时参数）三个顶级段

### Modified Capabilities
- `system-context`: `MAX_TOOL_ITERATIONS` 和 `CONTEXT_SAFE_LIMIT` 从 Python 常量迁移到 `config.yaml` 的 `agent.max_iterations` 和 `agent.context_safe_limit`

## Impact

- `config/configs.py`: 重构为 YAML 加载器，常量替换为配置属性
- `config/config.json`: 废弃删除
- `config/config.example.yaml`: 新增模板文件（不含 secrets）
- `agentd/providers/__init__.py`: `get_provider()` 适配新配置结构，支持多 provider 分发
- `agentd/bootstrap/container.py`: 适配新配置对象
- `cli/cli.py`: `MODEL` 字典 → 配置对象属性
- `agentd/prompt/prompts.py`: 同上
- `agentd/agent/runner.py`: `MAX_TOOL_ITERATIONS` → `config.agent.max_iterations`
- `agentd/context/context.py`: `CONTEXT_SAFE_LIMIT` → `config.agent.context_safe_limit`
