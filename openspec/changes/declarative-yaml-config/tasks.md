## Task 1: Create Config dataclass and YAML loader

- [x] Add `pyyaml` to `requirements.txt`
- [x] Rewrite `config/configs.py`: create `Config`/`ModelConfig`/`ProviderConfig`/`ToolsetsConfig`/`AgentConfig` dataclasses
- [x] Implement `load_config(path)` — read YAML, validate, return Config
- [x] Create module-level singleton via `get_config()` (lazy-loaded)
- [x] Keep backward compat aliases via PEP 562 `__getattr__`: `WORKDIR`, `WORKSPACE_DIR`, `BOOTSTRAP_FILES`, `MAX_FILE_CHARS`, `MAX_TOTAL_CHARS`, `MAX_SKILLS`, `MAX_SKILLS_PROMPT`
- [x] Create `config.example.yaml` (no secrets, committed to git)
- [x] Update `.gitignore`: add `config.yaml`, remove `config.json` line

## Task 2: Adapt provider factory for multi-provider dispatch

- [x] Rewrite `agentd/providers/__init__.py`: `get_provider(config)` reads `config.model` to match default provider
- [x] Support `api_key_env` — API key already injected by `load_config()`, factory reads from `provider_cfg.api_key`

## Task 3: Update all consumers to use new Config object

- [x] Update `agentd/bootstrap/container.py`: comment changed; `get_model_provider()` works via existing import
- [x] Update `agentd/context/context.py`: `CONTEXT_SAFE_LIMIT` → resolved via `__getattr__` to `config.agent.context_safe_limit`
- [x] Update `agentd/agent/runner.py`: `MAX_TOOL_ITERATIONS` → resolved via `__getattr__` to `config.agent.max_iterations`
- [x] Update `cli/cli.py`: `MODEL['name']` → `MODEL.default`
- [x] Update `agentd/prompt/prompts.py`: `MODEL['name']` → `MODEL.default`
- [x] No remaining `MODEL[...]` references in code

## Task 4: Cleanup old config and verify

- [x] Delete `config.json`
- [x] Verify provider loads correctly: model name from config, API key from env var
- [x] Verify agent parameters: `max_iterations` and `context_safe_limit` from YAML
- [x] All imports verified: Model, Provider, ContextGuard, AgentRunner all load correctly
