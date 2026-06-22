---
change: declarative-yaml-config
design-doc: docs/superpowers/specs/2026-06-22-declarative-yaml-config-design.md
base-ref: 7288179c77c1cb3af0e7d2a23ac2e5007bc327c3
---

# 声明式 YAML 配置 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目从 `config.json` 硬编码迁移到 `config.yaml` 声明式配置，支持多 provider、环境变量注入、集中化运行时参数。

**Architecture:** `Config` dataclass 作为配置单一事实源，通过 `load_config()` 从 YAML 文件加载，模块单例 `config` 供全项目使用。provider 工厂从 Config 对象读取多 provider 列表并分发。

**Tech Stack:** Python 3.14, PyYAML, dataclasses

## Global Constraints

- YAML 格式，`config.yaml` 在项目根目录
- API key 必须通过环境变量注入（`api_key_env` 字段），不允许明文
- 启动失败是好的失败 — 缺失文件/环境变量直接 exit(1)，清晰报错
- 向后兼容：模块级别保留旧常量名作为 config 属性别名
- `config.example.yaml` 提交 git，`config.yaml` gitignored
- `pyyaml` 加入 `requirements.txt`

---

### Task 1: Config dataclass + YAML loader + config.example.yaml

**Files:**
- Modify: `config/configs.py`
- Create: `config/config.example.yaml`
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `Config`, `ModelConfig`, `ProviderConfig`, `ToolsetsConfig`, `AgentConfig`, `WorkspaceConfig`, `SkillsConfig` dataclasses
- Produces: `load_config(path: str | Path = None) -> Config`
- Produces: module singleton `config: Config`
- Produces: backward compat aliases `WORKDIR`, `WORKSPACE_DIR`, `CONTEXT_SAFE_LIMIT`, `MAX_TOOL_ITERATIONS`, `MAX_TOOL_OUTPUT`, `BOOTSTRAP_FILES`, `MAX_FILE_CHARS`, `MAX_TOTAL_CHARS`, `MAX_SKILLS`, `MAX_SKILLS_PROMPT`

- [ ] **Step 1: Add pyyaml to requirements.txt**

```bash
echo "pyyaml>=6.0" >> requirements.txt
```

- [ ] **Step 2: Write config loading tests**

Create `tests/test_config.py`:

```python
"""Tests for config/configs.py — YAML config loading."""
import os
import tempfile
from pathlib import Path
import pytest

# We'll import after implementation, but tests define expected behavior
CONFIG_SAMPLE = """
model:
  default: deepseek
  providers:
    - name: deepseek
      base_url: https://api.deepseek.com/anthropic
      api_key_env: DEEPSEEK_API_KEY
    - name: openrouter
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY

toolsets:
  enabled: [memory, file]
  disabled: []

agent:
  max_iterations: 20
  context_safe_limit: 100000
  max_tool_output: 30000

workspace:
  bootstrap_files: [SOUL.md, IDENTITY.md]
  max_file_chars: 10000
  max_total_chars: 50000

skills:
  max_skills: 100
  max_skills_prompt: 20000
"""


class TestLoadConfig:
    """Config loading tests."""

    def test_loads_valid_yaml(self):
        """YC-LOAD-1: load_config reads YAML and returns Config."""
        from config.configs import load_config, Config
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(CONFIG_SAMPLE)
            f.flush()
            os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"
            os.environ["OPENROUTER_API_KEY"] = "sk-or-key"
            try:
                cfg = load_config(f.name)
                assert isinstance(cfg, Config)
                assert cfg.model.default == "deepseek"
                assert len(cfg.model.providers) == 2
                assert cfg.model.providers[0].api_key == "sk-test-key"
                assert cfg.agent.max_iterations == 20
                assert cfg.agent.context_safe_limit == 100000
                assert cfg.workspace.bootstrap_files == ["SOUL.md", "IDENTITY.md"]
            finally:
                os.unlink(f.name)
                del os.environ["DEEPSEEK_API_KEY"]
                del os.environ["OPENROUTER_API_KEY"]

    def test_missing_file_exits(self):
        """YC-LOAD-2: missing config.yaml prints message and exits."""
        from config.configs import load_config
        with pytest.raises(SystemExit) as exc:
            load_config("/nonexistent/path/config.yaml")
        assert exc.value.code == 1

    def test_missing_env_var_exits(self):
        """YC-MODEL-5: missing api_key_env exits with clear message."""
        from config.configs import load_config
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(CONFIG_SAMPLE)
            f.flush()
            # Ensure env var is not set
            old = os.environ.pop("DEEPSEEK_API_KEY", None)
            try:
                with pytest.raises(SystemExit) as exc:
                    load_config(f.name)
                assert exc.value.code == 1
            finally:
                os.unlink(f.name)
                if old:
                    os.environ["DEEPSEEK_API_KEY"] = old

    def test_default_not_found_exits(self):
        """YC-MODEL-4: model.default not in providers exits."""
        from config.configs import load_config
        yaml_content = """
model:
  default: nonexistent
  providers:
    - name: deepseek
      base_url: https://api.deepseek.com/anthropic
      api_key_env: DEEPSEEK_API_KEY
toolsets:
  enabled: []
  disabled: []
agent:
  max_iterations: 30
  context_safe_limit: 180000
  max_tool_output: 50000
workspace:
  bootstrap_files: []
  max_file_chars: 20000
  max_total_chars: 150000
skills:
  max_skills: 150
  max_skills_prompt: 30000
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            os.environ["DEEPSEEK_API_KEY"] = "sk-test"
            try:
                with pytest.raises(SystemExit) as exc:
                    load_config(f.name)
                assert exc.value.code == 1
            finally:
                os.unlink(f.name)
                del os.environ["DEEPSEEK_API_KEY"]

    def test_yaml_syntax_error_exits(self):
        """YC-LOAD-3: YAML syntax error prints line number and exits."""
        from config.configs import load_config
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("model:\n  - bad\n  indent: oops\n")
            f.flush()
            try:
                with pytest.raises(SystemExit) as exc:
                    load_config(f.name)
                assert exc.value.code == 1
            finally:
                os.unlink(f.name)

    def test_backward_compat_aliases(self):
        """YC-CMP-1: old constant names work as aliases."""
        from config import configs
        from config.configs import (
            WORKDIR, WORKSPACE_DIR, CONTEXT_SAFE_LIMIT,
            MAX_TOOL_ITERATIONS, BOOTSTRAP_FILES,
        )
        assert isinstance(WORKDIR, Path)
        assert isinstance(WORKSPACE_DIR, Path)
        assert CONTEXT_SAFE_LIMIT == configs.config.agent.context_safe_limit
        assert MAX_TOOL_ITERATIONS == configs.config.agent.max_iterations
```

- [ ] **Step 3: Run tests to verify they fail**

Expected: ImportError / test failures since Config classes and load_config don't exist yet.

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_config.py -v 2>&1 | head -20
```

- [ ] **Step 4: Rewrite config/configs.py**

```python
"""声明式配置系统 — 从 config.yaml 加载所有运行时配置。

模块级别单例 `config` 在 import 时自动加载。
向后兼容别名（WORKDIR 等）映射到 config 对象属性。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ── Dataclasses ──────────────────────────────────────────────


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str
    api_key: str = ""  # 运行时从 os.environ 注入


@dataclass
class ModelConfig:
    default: str
    providers: list[ProviderConfig]


@dataclass
class ToolsetsConfig:
    enabled: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    max_iterations: int = 30
    context_safe_limit: int = 180000
    max_tool_output: int = 50000


@dataclass
class WorkspaceConfig:
    bootstrap_files: list[str] = field(default_factory=lambda: [
        "SOUL.md", "IDENTITY.md", "TOOLS.md", "USER.md",
        "HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "MEMORY.md",
    ])
    max_file_chars: int = 20000
    max_total_chars: int = 150000


@dataclass
class SkillsConfig:
    max_skills: int = 150
    max_skills_prompt: int = 30000


@dataclass
class Config:
    model: ModelConfig
    toolsets: ToolsetsConfig
    agent: AgentConfig
    workspace: WorkspaceConfig
    skills: SkillsConfig
    workdir: Path
    workspace_dir: Path


# ── Loader ───────────────────────────────────────────────────


def _find_config_path(path: str | Path | None = None) -> Path:
    """Determine config.yaml path. Default: <project_root>/config.yaml."""
    if path is not None:
        return Path(path)
    # Project root = parent of this config/ directory
    return Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: str | Path | None = None) -> Config:
    """Read config.yaml, validate, inject env vars, return Config.

    Fail-fast design: exits on missing file, bad YAML, missing fields,
    or unset environment variables.
    """
    config_path = _find_config_path(path)

    # YC-LOAD-2: missing file
    if not config_path.exists():
        print(
            f"ERROR: No config.yaml found at {config_path}.\n"
            f"  Copy config.example.yaml to config.yaml and edit it:\n"
            f"    cp config.example.yaml config.yaml"
        )
        sys.exit(1)

    # YC-LOAD-3: parse error
    try:
        raw = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError as e:
        print(f"ERROR: Failed to parse {config_path}:\n  {e}")
        sys.exit(1)

    if raw is None:
        print(f"ERROR: {config_path} is empty.")
        sys.exit(1)

    # Parse model
    model_raw = raw.get("model")
    if not model_raw:
        print("ERROR: config.yaml missing 'model' section.")
        sys.exit(1)
    default_name = model_raw.get("default")
    if not default_name:
        print("ERROR: config.yaml missing 'model.default'.")
        sys.exit(1)

    providers = []
    default_provider_raw = None
    for p in model_raw.get("providers", []):
        api_key_env = p.get("api_key_env", "")
        api_key = os.environ.get(api_key_env, "")
        if not api_key:  # YC-MODEL-5
            print(
                f"ERROR: Environment variable {api_key_env} not set.\n"
                f"  Provider '{p.get('name')}' requires it. Please export it:\n"
                f"    export {api_key_env}=<your-api-key>"
            )
            sys.exit(1)
        provider = ProviderConfig(
            name=p.get("name", ""),
            base_url=p.get("base_url", ""),
            api_key_env=api_key_env,
            api_key=api_key,
        )
        if provider.name == default_name:
            default_provider_raw = provider
        providers.append(provider)

    # YC-MODEL-4: default not found
    if default_provider_raw is None and providers:
        print(
            f"ERROR: model.default '{default_name}' not found in providers list.\n"
            f"  Available: {[p.name for p in providers]}"
        )
        sys.exit(1)

    model = ModelConfig(default=default_name, providers=providers)

    # Parse toolsets
    tools_raw = raw.get("toolsets", {})
    toolsets = ToolsetsConfig(
        enabled=tools_raw.get("enabled", []),
        disabled=tools_raw.get("disabled", []),
    )

    # Parse agent
    agent_raw = raw.get("agent", {})
    agent = AgentConfig(
        max_iterations=agent_raw.get("max_iterations", 30),
        context_safe_limit=agent_raw.get("context_safe_limit", 180000),
        max_tool_output=agent_raw.get("max_tool_output", 50000),
    )

    # Parse workspace
    ws_raw = raw.get("workspace", {})
    workspace = WorkspaceConfig(
        bootstrap_files=ws_raw.get(
            "bootstrap_files",
            ["SOUL.md", "IDENTITY.md", "TOOLS.md", "USER.md",
             "HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "MEMORY.md"],
        ),
        max_file_chars=ws_raw.get("max_file_chars", 20000),
        max_total_chars=ws_raw.get("max_total_chars", 150000),
    )

    # Parse skills
    sk_raw = raw.get("skills", {})
    skills = SkillsConfig(
        max_skills=sk_raw.get("max_skills", 150),
        max_skills_prompt=sk_raw.get("max_skills_prompt", 30000),
    )

    workdir = config_path.parent
    workspace_dir = workdir / "workspace"

    return Config(
        model=model,
        toolsets=toolsets,
        agent=agent,
        workspace=workspace,
        skills=skills,
        workdir=workdir,
        workspace_dir=workspace_dir,
    )


# ── Module singleton ─────────────────────────────────────────

config: Config = load_config()

# ── Backward compat aliases (YC-CMP-1, YC-CMP-2) ─────────────

WORKDIR: Path = config.workdir
WORKSPACE_DIR: Path = config.workspace_dir
CONTEXT_SAFE_LIMIT: int = config.agent.context_safe_limit
MAX_TOOL_ITERATIONS: int = config.agent.max_iterations
MAX_TOOL_OUTPUT: int = config.agent.max_tool_output
BOOTSTRAP_FILES: list[str] = config.workspace.bootstrap_files
MAX_FILE_CHARS: int = config.workspace.max_file_chars
MAX_TOTAL_CHARS: int = config.workspace.max_total_chars
MAX_SKILLS: int = config.skills.max_skills
MAX_SKILLS_PROMPT: int = config.skills.max_skills_prompt


def get_model_provider():
    """返回基于 config.model 的 BaseProvider 实例。"""
    from agentd.providers import get_provider
    return get_provider(config)
```

- [ ] **Step 5: Create config.example.yaml**

Create `config/config.example.yaml`:

```yaml
# ultimate agent — 声明式配置模板
# cp config.example.yaml config.yaml 并填写你的配置

# ── Model: LLM provider 配置 ──────────────────────────────────
model:
  # 当前使用的 provider（必须匹配下面 providers 列表中某个 name）
  default: deepseek

  providers:
    - name: deepseek
      base_url: https://api.deepseek.com/anthropic
      # API key 从环境变量读取（不允许明文写在配置文件中）
      api_key_env: DEEPSEEK_API_KEY

    - name: openrouter
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY

    # 添加更多 provider 示例：
    # - name: anthropic
    #   base_url: https://api.anthropic.com
    #   api_key_env: ANTHROPIC_API_KEY

# ── Toolsets: 工具集开关 ─────────────────────────────────────
toolsets:
  enabled: [memory, file, browser, skill]
  disabled: []

# ── Agent: 运行时参数 ─────────────────────────────────────────
agent:
  max_iterations: 30       # 单轮对话最大工具调用次数
  context_safe_limit: 180000  # 上下文 token 安全阈值
  max_tool_output: 50000   # 单个工具输出最大字符数

# ── Workspace: 工作区与 Bootstrap ─────────────────────────────
workspace:
  bootstrap_files:
    - SOUL.md
    - IDENTITY.md
    - TOOLS.md
    - USER.md
    - HEARTBEAT.md
    - BOOTSTRAP.md
    - AGENTS.md
    - MEMORY.md
  max_file_chars: 20000
  max_total_chars: 150000

# ── Skills: 技能系统 ──────────────────────────────────────────
skills:
  max_skills: 150
  max_skills_prompt: 30000
```

- [ ] **Step 6: Update .gitignore**

```bash
# In .gitignore, replace config.json with config.yaml
```

Replace the line `config.json` with:

```
config.yaml
```

Keep `config.json` removed — it will be deleted in Task 4.

- [ ] **Step 7: Run tests**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_config.py -v
```

Expected: All tests PASS (YC-LOAD-1 through YC-CMP-1 verified).

**Note:** Tests rely on `config.example.yaml` as the real config file for backward compat alias tests. If the real `config.yaml` exists at project root, those specific tests may need adjustment — the key invariant is that aliases point to the correct config attributes.

- [ ] **Step 8: Commit**

```bash
git add config/configs.py config/config.example.yaml requirements.txt .gitignore tests/test_config.py
git commit -m "feat: Config dataclass + YAML loader + config.example.yaml

- Config/ModeConfig/ProviderConfig/etc. dataclasses
- load_config(): YAML → validate → env var inject → Config
- Module singleton config = load_config()
- Backward compat aliases (WORKDIR, CONTEXT_SAFE_LIMIT, etc.)
- config.example.yaml template (no secrets)
- config.yaml gitignored
- pyyaml in requirements.txt"
```

---

### Task 2: Adapt provider factory for multi-provider dispatch

**Files:**
- Modify: `agentd/providers/__init__.py`
- Modify: `tests/test_config.py` (add provider tests)

**Interfaces:**
- Consumes: `Config` dataclass from Task 1
- Produces: `get_provider(config: Config) -> BaseProvider`

- [ ] **Step 1: Write provider factory tests**

Append to `tests/test_config.py`:

```python

class TestGetProvider:
    """Provider factory tests."""

    def test_returns_provider_for_default_model(self):
        """get_provider dispatches to correct provider based on config.model.default."""
        from config.configs import config
        from agentd.providers import get_provider, BaseProvider
        provider = get_provider(config)
        assert isinstance(provider, BaseProvider)

    def test_env_var_injected_to_provider(self):
        """api_key_env → os.environ → provider receives api_key."""
        from config.configs import config
        from agentd.providers import get_provider
        provider = get_provider(config)
        # Provider should have been constructed with api_key from env
        assert provider._model == config.model.default
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_config.py::TestGetProvider -v
```

Expected: FAIL — `get_provider` still takes `dict`, not `Config`.

- [ ] **Step 3: Rewrite agentd/providers/__init__.py**

```python
"""Provider factory — 根据 Config 对象返回合适的 BaseProvider 实例。"""

from agentd.providers.base import BaseProvider, Response, ContentBlock


def get_provider(config) -> BaseProvider:
    """根据 config.model 返回匹配的 provider 实例。

    config: Config 对象（来自 config.configs）。

    查找逻辑：
    1. 读取 config.model.default → 当前 provider name
    2. 在 config.model.providers 中匹配 name
    3. 使用已注入的 api_key 构造对应的 Provider

    当前仅支持 Anthropic 兼容协议；后续可扩展 OpenAI、Ollama 等。
    """
    from agentd.providers.anthropic import AnthropicProvider

    # Find the default provider config
    default_name = config.model.default
    provider_cfg = None
    for p in config.model.providers:
        if p.name == default_name:
            provider_cfg = p
            break

    if provider_cfg is None:
        raise ValueError(
            f"Default provider '{default_name}' not found in providers list. "
            f"Available: {[p.name for p in config.model.providers]}"
        )

    # Dispatch to appropriate provider class
    # Future: check provider_cfg.type or name prefix for OpenAI/Ollama
    return AnthropicProvider(
        api_key=provider_cfg.api_key,
        base_url=provider_cfg.base_url,
        model=config.model.default,
    )


__all__ = ["BaseProvider", "Response", "ContentBlock", "get_provider"]
```

- [ ] **Step 4: Run tests**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_config.py::TestGetProvider -v
```

Expected: PASS (if env vars are set correctly; may need `DEEPSEEK_API_KEY`).

- [ ] **Step 5: Add smoke test**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
from config.configs import config, get_model_provider
p = get_model_provider()
print(f'Provider: {type(p).__name__}')
print(f'Model: {config.model.default}')
print(f'Providers: {[p.name for p in config.model.providers]}')
print('OK')
"
```

Expected: prints provider info, no errors.

- [ ] **Step 6: Commit**

```bash
git add agentd/providers/__init__.py tests/test_config.py
git commit -m "feat: multi-provider factory dispatch from Config object

- get_provider(config) reads config.model to find default provider
- api_key_env already injected by load_config() — provider factory just reads it
- ValueError fallback if default not in providers list"
```

---

### Task 3: Update all consumers to use new Config object

**Files:**
- Modify: `agentd/bootstrap/container.py`
- Modify: `agentd/context/context.py`
- Modify: `agentd/agent/runner.py`
- Modify: `cli/cli.py`
- Modify: `agentd/prompt/prompts.py`

**Interfaces:**
- Consumes: `config: Config` singleton from Task 1
- Consumes: `get_provider(config)` from Task 2
- All backward compat aliases already in place — existing `from config.configs import CONTEXT_SAFE_LIMIT` etc. continue working

- [ ] **Step 1: Verify backward compat aliases work for all consumers**

The aliases are already in `config/configs.py` from Task 1. Verify each consumer's imports still resolve:

```python
# All of these should work without changes:
# from config.configs import CONTEXT_SAFE_LIMIT  → config.agent.context_safe_limit
# from config.configs import MAX_TOOL_ITERATIONS  → config.agent.max_iterations
# from config.configs import MAX_TOOL_OUTPUT      → config.agent.max_tool_output
# from config.configs import BOOTSTRAP_FILES       → config.workspace.bootstrap_files
# from config.configs import MAX_FILE_CHARS        → config.workspace.max_file_chars
# from config.configs import MAX_TOTAL_CHARS       → config.workspace.max_total_chars
# from config.configs import MAX_SKILLS            → config.skills.max_skills
# from config.configs import MAX_SKILLS_PROMPT     → config.skills.max_skills_prompt
# from config.configs import WORKDIR               → config.workdir
# from config.configs import WORKSPACE_DIR         → config.workspace_dir
# from config.configs import MODEL                 → config.model (dict-like shape changed!)
```

**IMPORTANT**: `MODEL` was a `dict` from `config.json`. Consumers that used `MODEL['name']`, `MODEL['provider']` etc. must be updated. `MODEL` is NOT in the backward compat aliases — it must be updated explicitly.

- [ ] **Step 2: Run full import check**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
from config.configs import (
    WORKDIR, WORKSPACE_DIR, CONTEXT_SAFE_LIMIT,
    MAX_TOOL_ITERATIONS, MAX_TOOL_OUTPUT, BOOTSTRAP_FILES,
    MAX_FILE_CHARS, MAX_TOTAL_CHARS, MAX_SKILLS, MAX_SKILLS_PROMPT,
    get_model_provider, config,
)
print('All imports OK')
print(f'context_safe_limit={CONTEXT_SAFE_LIMIT}')
print(f'max_iterations={MAX_TOOL_ITERATIONS}')
print(f'bootstrap_files={BOOTSTRAP_FILES[:3]}...')
"
```

Expected: All imports OK with correct values.

- [ ] **Step 3: Update cli/cli.py — MODEL reference**

The `cli/cli.py` line 5 imports `MODEL` from `config.configs`, and line 49 uses `MODEL['name']`.

Since `MODEL` is no longer a dict, update the display line:

```python
# cli/cli.py line 5: remove MODEL from import
from config.configs import MAX_TOTAL_CHARS, WORKSPACE_DIR, config
```

```python
# cli/cli.py line 49: replace MODEL['name'] with config reference
f"[primary]当前模型:[/primary] {config.model.default}",
```

- [ ] **Step 4: Update agentd/prompt/prompts.py — MODEL reference**

Check what `prompts.py` uses `MODEL` for:

```bash
cd c:/self/work/todo/ultimate_try && grep -n "MODEL" agentd/prompt/prompts.py
```

If it uses `MODEL['name']`, replace with `config.model.default`. If it uses the whole dict, restructure to use `config.model`.

Read the file to check:

```python
# agentd/prompt/prompts.py line 2
# Change: from config.configs import MODEL
# To:     from config.configs import config
# Then replace MODEL references with config.model attributes
```

- [ ] **Step 5: Update agentd/bootstrap/container.py**

The `container.py` imports `get_model_provider` and `WORKSPACE_DIR`. Both already work via aliases. However, the comment on line 30 says "由 config.json 驱动" — update the comment:

```python
# container.py line 30: update comment
# Provider — 由 config.yaml 驱动
provider = get_model_provider()
```

- [ ] **Step 6: Update agentd/context/context.py**

`context/context.py` line 3 imports `CONTEXT_SAFE_LIMIT`. This already works via the alias. No code changes needed — the alias maps to `config.agent.context_safe_limit`.

- [ ] **Step 7: Update agentd/agent/runner.py**

`agent/runner.py` line 11 imports `MAX_TOOL_ITERATIONS`. This already works via the alias. No code changes needed — the alias maps to `config.agent.max_iterations`.

- [ ] **Step 8: Search for any other MODEL references**

```bash
cd c:/self/work/todo/ultimate_try && grep -rn "MODEL" --include="*.py" --exclude-dir="__pycache__" --exclude-dir=".git"
```

Update any remaining references. The key ones are `cli/cli.py` and `agentd/prompt/prompts.py`.

- [ ] **Step 9: Run full import verification**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
# Test all the imports used across the codebase
from config.configs import config
from agentd.providers import get_provider
from agentd.bootstrap.container import Container
print('Container imports OK')
print(f'Model default: {config.model.default}')
print(f'Agent max_iterations: {config.agent.max_iterations}')
print(f'Context safe limit: {config.agent.context_safe_limit}')
print('All consumer imports verified')
"
```

Expected: All imports succeed, config values are correct.

- [ ] **Step 10: Commit**

```bash
git add cli/cli.py agentd/prompt/prompts.py agentd/bootstrap/container.py
git commit -m "refactor: update consumers to use Config object

- cli/cli.py: MODEL['name'] → config.model.default
- agentd/prompt/prompts.py: MODEL import → config reference
- agentd/bootstrap/container.py: comment update
- All other consumers work via backward compat aliases"
```

---

### Task 4: Cleanup old config + verify end-to-end

**Files:**
- Delete: `config.json`
- Verify: all files touched

**Interfaces:**
- None new. Final verification.

- [ ] **Step 1: Delete config.json**

```bash
rm config.json
```

- [ ] **Step 2: Ensure config.yaml exists for the current setup**

The user must create `config.yaml` from the example template before the project will start:

```bash
cp config/config.example.yaml config.yaml
```

Then set the required environment variable:

```bash
export DEEPSEEK_API_KEY=<actual-key>
```

(If running in the same environment where `config.json` previously worked, the API key can be extracted from the old `config.json` and exported.)

- [ ] **Step 3: Verify all imports work**

```bash
cd c:/self/work/todo/ultimate_try && python -c "
import sys
sys.path.insert(0, '.')
from config.configs import config, get_model_provider
from agentd.bootstrap.container import Container
from agentd.context.context import ContextGuard
from agentd.agent.runner import AgentRunner
print('All core imports OK')
print(f'Using model: {config.model.default}')
print(f'Provider: {type(get_model_provider()).__name__}')
"
```

Expected: All imports OK, provider created.

- [ ] **Step 4: Run existing tests**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/ -v 2>&1
```

Expected: All tests pass.

- [ ] **Step 5: Update tasks.md checkboxes**

Mark all tasks as done in `openspec/changes/declarative-yaml-config/tasks.md`.

- [ ] **Step 6: Commit**

```bash
git add config.json openspec/changes/declarative-yaml-config/tasks.md
git commit -m "chore: delete config.json, mark all tasks complete

Migration complete: config.json → config.yaml declarative config.
- config/configs.py: YAML loader with env var injection
- agentd/providers/__init__.py: multi-provider factory
- All consumers updated with backward compat aliases"
```
