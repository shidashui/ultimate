# Comet Design Handoff

- Change: declarative-yaml-config
- Phase: design
- Mode: compact
- Context hash: ac14788d44f470429e988b2aa1b4662bb4364c920f95b2ea0cfeaeee5cfa78b3

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

## openspec/changes/declarative-yaml-config/specs/system-context/spec.md

- Source: openspec/changes/declarative-yaml-config/specs/system-context/spec.md
- Lines: 1-20
- SHA256: 1f58e5242696dbc1165a5cca0937809616289c0533f60ab2398032e977ab2da1

```md
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
```

## openspec/changes/declarative-yaml-config/specs/yaml-config/spec.md

- Source: openspec/changes/declarative-yaml-config/specs/yaml-config/spec.md
- Lines: 1-61
- SHA256: e34b7df9212407455f1d984cce195fdf3beb04b2f879f263323ad8425ae7d551

```md
# YAML Config — 声明式配置系统

## ADDED Requirements

### YC-LOAD: 配置加载

- **YC-LOAD-1**: `load_config(path)` 从 YAML 文件读取配置，返回 `Config` dataclass 实例
- **YC-LOAD-2**: 文件缺失时打印 "Copy config.example.yaml to config.yaml and edit." 并 exit(1)
- **YC-LOAD-3**: YAML 语法错误时打印行号和具体错误信息，exit(1)
- **YC-LOAD-4**: 必填字段缺失时打印字段完整路径（如 `model.default`），exit(1)
- **YC-LOAD-5**: 默认从项目根目录加载 `config.yaml`，`WORKDIR` 定位

### YC-MODEL: Model 配置段

- **YC-MODEL-1**: `model.default` 指定当前使用的 provider name
- **YC-MODEL-2**: `model.providers` 为 provider 列表，每项含 `name`、`base_url`、`api_key_env`
- **YC-MODEL-3**: 启动时从 `os.environ[provider.api_key_env]` 读取 API key，注入 `provider.api_key`
- **YC-MODEL-4**: `model.default` 指定的 provider 不在 providers 列表中时报错
- **YC-MODEL-5**: `api_key_env` 环境变量未设置时打印 "[NAME]_API_KEY not set. Please export it." 并 exit(1)

### YC-AGENT: Agent 配置段

- **YC-AGENT-1**: `agent.max_iterations` 控制工具调用上限，默认 30
- **YC-AGENT-2**: `agent.context_safe_limit` 控制上下文安全阈值，默认 180000
- **YC-AGENT-3**: `agent.max_tool_output` 控制单个工具输出最大字符数，默认 50000

### YC-TOOLSETS: Toolsets 配置段

- **YC-TOOL-1**: `toolsets.enabled` 列出启用的工具集
- **YC-TOOL-2**: `toolsets.disabled` 列出禁用的工具集

### YC-WORKSPACE: Workspace 配置段

- **YC-WS-1**: `workspace.bootstrap_files` 控制启动时加载的 Bootstrap 文件列表
- **YC-WS-2**: `workspace.max_file_chars` 控制单文件最大字符数
- **YC-WS-3**: `workspace.max_total_chars` 控制 Bootstrap 文件总字符上限

### YC-SKILLS: Skills 配置段

- **YC-SK-1**: `skills.max_skills` 控制最大技能数
- **YC-SK-2**: `skills.max_skills_prompt` 控制技能提示词最大长度

### YC-TEMPLATE: 模板文件

- **YC-TPL-1**: 提供 `config.example.yaml` 作为用户模板，包含所有默认值
- **YC-TPL-2**: `config.example.yaml` 不含 secrets，可安全提交到 git
- **YC-TPL-3**: `config.yaml` 加入 `.gitignore`

### YC-COMPAT: 向后兼容

- **YC-CMP-1**: 模块级别保留旧常量名作为 `config` 对象属性别名（`WORKDIR`、`CONTEXT_SAFE_LIMIT`、`MAX_TOOL_ITERATIONS` 等）
- **YC-CMP-2**: 现有 `from config.configs import ...` 语句继续有效

## 验收场景

1. **正常加载**: `config.yaml` 存在且格式正确 → `load_config()` 返回完整 Config 对象
2. **缺失文件**: `config.yaml` 不存在 → 打印模板提示 → exit(1)
3. **缺失环境变量**: `api_key_env` 指定的环境变量未设置 → 打印变量名 → exit(1)
4. **default 不匹配**: `model.default` 指向不存在的 provider → 打印错误 → exit(1)
5. **YAML 语法错误**: 缩进或格式错误 → 打印行号 + 错误 → exit(1)
6. **模板可用**: `cp config.example.yaml config.yaml` → 填写 api_key_env 对应环境变量 → 正常启动
```

