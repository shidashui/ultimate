# System Context — Delta: 配置源迁移

## 变更说明

`MAX_TOOL_ITERATIONS` 和 `CONTEXT_SAFE_LIMIT` 的配置源从 `config/configs.py` Python 常量迁移到 `config.yaml` 的 `agent` 段。

## MODIFIED Requirements

### SC-BUDGET: 迭代预算 (修改)

- **SC-BUD-4**: 默认上限 `MAX_TOOL_ITERATIONS = 30`，通过 `config.yaml` 的 `agent.max_iterations` 配置（原通过 `config/configs.py` 配置）

### SC-PREFLIGHT: 预飞上下文压缩 (修改)

- **SC-PF-2**: 阈值从 `max_tokens * 0.8` 调整：`ContextGuard.max_tokens` 默认值来自 `config.yaml` 的 `agent.context_safe_limit`（原通过 `config/configs.py` 的 `CONTEXT_SAFE_LIMIT` 常量）

## 验收场景（更新）

1. **配置驱动**: `config.yaml` `agent.max_iterations: 20` → AgentRunner 预算上限为 20
2. **配置驱动**: `config.yaml` `agent.context_safe_limit: 100000` → ContextGuard 阈值为 100000 * 0.8
