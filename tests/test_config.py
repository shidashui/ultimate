"""Tests for config/configs.py — YAML config loading."""
import os
import tempfile
from pathlib import Path
import pytest


def _temp_yaml(content: str) -> str:
    """Write content to a temp file, return path. Caller handles cleanup."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    )
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return tmp.name


def _cleanup(path: str) -> None:
    """Delete a temp file, handling Windows file locking."""
    try:
        os.unlink(path)
    except PermissionError:
        pass


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

        path = _temp_yaml(CONFIG_SAMPLE)
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"
        os.environ["OPENROUTER_API_KEY"] = "sk-or-key"
        try:
            cfg = load_config(path)
            assert isinstance(cfg, Config)
            assert cfg.model.default == "deepseek"
            assert len(cfg.model.providers) == 2
            assert cfg.model.providers[0].api_key == "sk-test-key"
            assert cfg.agent.max_iterations == 20
            assert cfg.agent.context_safe_limit == 100000
            assert cfg.workspace.bootstrap_files == ["SOUL.md", "IDENTITY.md"]
        finally:
            del os.environ["DEEPSEEK_API_KEY"]
            del os.environ["OPENROUTER_API_KEY"]
            _cleanup(path)

    def test_missing_file_exits(self):
        """YC-LOAD-2: missing config.yaml prints message and exits."""
        from config.configs import load_config

        with pytest.raises(SystemExit) as exc:
            load_config("/nonexistent/path/config.yaml")
        assert exc.value.code == 1

    def test_missing_env_var_exits(self):
        """YC-MODEL-5: missing api_key_env exits with clear message."""
        from config.configs import load_config

        path = _temp_yaml(CONFIG_SAMPLE)
        old = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            with pytest.raises(SystemExit) as exc:
                load_config(path)
            assert exc.value.code == 1
        finally:
            if old:
                os.environ["DEEPSEEK_API_KEY"] = old
            _cleanup(path)

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
        path = _temp_yaml(yaml_content)
        os.environ["DEEPSEEK_API_KEY"] = "sk-test"
        try:
            with pytest.raises(SystemExit) as exc:
                load_config(path)
            assert exc.value.code == 1
        finally:
            del os.environ["DEEPSEEK_API_KEY"]
            _cleanup(path)

    def test_yaml_syntax_error_exits(self):
        """YC-LOAD-3: YAML syntax error prints line number and exits."""
        from config.configs import load_config

        path = _temp_yaml("model:\n  - bad\n  indent: oops\n")
        try:
            with pytest.raises(SystemExit) as exc:
                load_config(path)
            assert exc.value.code == 1
        finally:
            _cleanup(path)
