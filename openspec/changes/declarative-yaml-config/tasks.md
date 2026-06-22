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
