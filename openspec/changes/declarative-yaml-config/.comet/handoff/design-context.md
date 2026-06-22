# Comet Design Handoff

- Change: declarative-yaml-config
- Phase: design
- Mode: compact
- Context hash: 6be4b6db3829a47d7ff03e9907bc239fc6bb6c5a96dce37fd9cf5f8e959cc302

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/declarative-yaml-config/proposal.md

- Source: openspec/changes/declarative-yaml-config/proposal.md
- Lines: 1-33
- SHA256: 8d3b32d28927752a37b1509353b80c1bab56d0ce891cff56c50fdcb624243a19

```md
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
```

## openspec/changes/declarative-yaml-config/design.md

- Source: openspec/changes/declarative-yaml-config/design.md
- Lines: 1-63
- SHA256: 260a0d1edc4940f497f21159e4d10c3547a1f01d950d15bcb3aa74a6a807b908

```md
## 设计决策

### 1. 配置格式：YAML

选用 YAML 而非 TOML/JSON 的理由：
- 注释支持（JSON 不支持，TOML 有限）
- Python 生态原生 `yaml` 库
- 可读性优于 JSON，层级比 TOML 直观
- `config.example.yaml` 可直接作为文档

### 2. 配置结构

```yaml
model:
  default: deepseek-v4-pro          # 当前使用的 provider
  providers:
    - name: deepseek
      base_url: https://api.deepseek.com/anthropic
      api_key_env: DEEPSEEK_API_KEY # 从环境变量读取，不写明文
    - name: openrouter
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY

toolsets:
  enabled: [memory, file, browser, skill]
  disabled: []

agent:
  max_iterations: 30
  context_safe_limit: 180000
```

### 3. Config 对象设计

`config/configs.py` 重构为配置加载器：

- `Config` dataclass 持有解析后的配置
- `load_config(path)` 函数：读取 YAML → 校验 → 返回 Config
- 模块级单例 `config = load_config("config.yaml")`
- 向后兼容：保留 `WORKDIR`、`WORKSPACE_DIR`、`BOOTSTRAP_FILES` 等路径常量

### 4. Provider 工厂适配

`get_provider()` 改为接收 Config 对象：
- 读取 `config.model.default` 找到当前 provider name
- 在 `config.model.providers` 列表中匹配 name
- 读取 `api_key_env` 环境变量获取 API key
- 后续新增 provider 只需在 `agentd/providers/` 添加实现 + YAML 配置

### 5. 迁移策略

- 删除 `config.json`
- 新增 `config.example.yaml`（不含 secrets，可提交 git）
- `config.yaml` 加入 `.gitignore`
- Python 硬编码常量（`CONTEXT_SAFE_LIMIT`、`MAX_TOOL_ITERATIONS`）迁移到 YAML

### 6. 风险

| 风险 | 缓解 |
|------|------|
| 现有 `config.json` 用户迁移 | `config.example.yaml` 提供模板；`config.yaml` gitignored |
| `yaml` 库可能未安装 | 在 `requirements.txt` 添加 `pyyaml` |
| 环境变量未设置导致启动失败 | `load_config()` 校验阶段给出明确错误信息 |
```

## openspec/changes/declarative-yaml-config/tasks.md

- Source: openspec/changes/declarative-yaml-config/tasks.md
- Lines: 1-30
- SHA256: d7b16d74de0790c6ad117f758794758dceccabbbf62607d74f2d48607fd2cb8c

```md
## Task 1: Create Config dataclass and YAML loader

- [ ] Add `pyyaml` to `requirements.txt`
- [ ] Rewrite `config/configs.py`: create `Config`/`ModelConfig`/`ProviderConfig`/`ToolsetsConfig`/`AgentConfig` dataclasses
- [ ] Implement `load_config(path)` — read YAML, validate, return Config
- [ ] Create module-level singleton `config = load_config("config.yaml")`
- [ ] Keep path constants: `WORKDIR`, `WORKSPACE_DIR`, `BOOTSTRAP_FILES`, `MAX_FILE_CHARS`, `MAX_TOTAL_CHARS`, `MAX_SKILLS`, `MAX_SKILLS_PROMPT`
- [ ] Create `config.example.yaml` (no secrets, committed to git)
- [ ] Update `.gitignore`: add `config.yaml`, remove `config.json` line

## Task 2: Adapt provider factory for multi-provider dispatch

- [ ] Rewrite `agentd/providers/__init__.py`: `get_provider(config)` reads `config.model` to match default provider
- [ ] Support `api_key_env` — read API key from environment variable

## Task 3: Update all consumers to use new Config object

- [ ] Update `agentd/bootstrap/container.py`: pass `config` to `get_provider()`
- [ ] Update `agentd/context/context.py`: `CONTEXT_SAFE_LIMIT` → `config.agent.context_safe_limit`
- [ ] Update `agentd/agent/runner.py`: `MAX_TOOL_ITERATIONS` → `config.agent.max_iterations`
- [ ] Update `cli/cli.py`: `MODEL['name']` → `config.model` attributes
- [ ] Update `agentd/prompt/prompts.py`: `MODEL` → config reference
- [ ] Update any remaining `from config.configs import MODEL` references

## Task 4: Cleanup old config and verify

- [ ] Delete `config.json`
- [ ] Run `python ultimate.py` (or project entry point) to verify startup
- [ ] Verify provider loads correctly: model name from config, API key from env var
- [ ] Verify agent parameters: `max_iterations` and `context_safe_limit` from YAML
```

