---
change: tool-call-param-repair
design-doc: docs/superpowers/specs/2026-06-23-tool-call-param-repair-design.md
base-ref: 1fce7004d7c20ebc7aa734f67652a6f26a46b6f0
archived-with: 2026-06-23-tool-call-param-repair
---

# Tool Call Parameter Validation & Auto-Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic parameter validation and repair in `process_tool_call()` so malformed LLM tool call inputs (wrong types, extra params, missing defaults) are fixed before calling the handler.

**Architecture:** Schema-driven type coercion (from `ToolRegistry`) combined with `inspect.signature` default extraction. New pure function `validate_and_repair()` in `agentd/tools/param_repair.py`. Integrated as a pre-call step in `AgentRunner.process_tool_call()`.

**Tech Stack:** Python 3.12+ stdlib (`inspect`, `contextvars`, `logging`), existing `ToolRegistry`

## Global Constraints

- Pure Python standard library — zero external dependencies
- Repair failures must return specific diagnostic errors, never silently swallow
- Existing `try/except TypeError` in `process_tool_call` preserved as safety net
- All repairs logged at `WARNING` level for observability
- 68 existing tests must continue to pass

archived-with: 2026-06-23-tool-call-param-repair
---

### Task 1: Add `get_tool_schema()` to ToolRegistry

**Files:**
- Modify: `agentd/tools/registry.py:52-53` (add method after `get_handlers`)

**Interfaces:**
- Consumes: `self._tools` (list of internal tool dicts)
- Produces: `get_tool_schema(name: str) -> dict | None` — used by Container in Task 2, by runner in Task 4

- [ ] **Step 1: Add the method**

```python
def get_tool_schema(self, name: str) -> dict | None:
    """返回 {param_name: {type, description}, ...} 或 None（未知工具）。"""
    for tool in self._tools:
        if tool["name"] == name:
            return tool["input_schema"]["properties"]
    return None
```

Insert after `get_handlers()` (after line 64) in `agentd/tools/registry.py`.

- [ ] **Step 2: Verify import works**

Run: `python -c "from agentd.tools.registry import registry; print(registry.get_tool_schema('bash'))"`
Expected: `{'command': {'type': 'string', 'description': '...'}, 'timeout': {'type': 'integer', 'description': '...'}}`

- [ ] **Step 3: Commit**

```bash
git add agentd/tools/registry.py
git commit -m "feat: add get_tool_schema(name) to ToolRegistry"
```

archived-with: 2026-06-23-tool-call-param-repair
---

### Task 2: Add `tools_schemas` property to Container

**Files:**
- Modify: `agentd/bootstrap/container.py` (add property)

**Interfaces:**
- Consumes: `self.tools` (list of tool schema dicts from BootstrapLoader)
- Produces: `tools_schemas: dict` — `{tool_name: {param: {type, description}}}` — used by runner in Task 4

- [ ] **Step 1: Add the property**

```python
@property
def tools_schemas(self) -> dict:
    """{tool_name: {param: {type, description}}} — 供 param_repair 做类型强转。"""
    return {t["name"]: t["input_schema"]["properties"] for t in self.tools}
```

Insert after the existing `tools_handlers` property in `agentd/bootstrap/container.py`.

- [ ] **Step 2: Verify**

Run: `python -c "from agentd.bootstrap import Container; c = Container(); print('bash' in c.tools_schemas)"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add agentd/bootstrap/container.py
git commit -m "feat: add tools_schemas property to Container"
```

archived-with: 2026-06-23-tool-call-param-repair
---

### Task 3: Create `agentd/tools/param_repair.py`

**Files:**
- Create: `agentd/tools/param_repair.py`

**Interfaces:**
- Consumes: (none — pure function, no imports from this project)
- Produces: `validate_and_repair(tool_input: dict, schema: dict[str, dict], handler: callable) -> tuple[dict, list[str]]` — used by runner in Task 4

- [ ] **Step 1: Create the module with full implementation**

```python
"""Tool call parameter validation and auto-repair.

Schema-driven type coercion + inspect-based default filling.
Pure function — no internal state, no side effects.
"""
from __future__ import annotations
import inspect
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── type coercion ────────────────────────────────────────────

_SCHEMA_TYPE_TO_PYTHON: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _coerce(value: Any, target_type: str) -> tuple[Any, str | None]:
    """尝试将 value 强转为 target_type 对应的 Python 类型。

    Returns:
        (coerced_value, warning_or_none)
    """
    py_type = _SCHEMA_TYPE_TO_PYTHON.get(target_type)
    if py_type is None:
        return value, None  # unknown schema type, pass through

    # 已是对应类型 → 无需修复
    if isinstance(value, py_type):
        # 但 bool 是 int 的子类, 需要特殊处理
        if py_type is int and isinstance(value, bool):
            return int(value), f"coerced bool → int ({value!r} → {int(value)})"
        return value, None

    # bool("False") == True — 字符串 "False" 非空即 True, 这不符合直觉
    if py_type is bool and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True, f"coerced str → bool ({value!r} → True)"
        if lowered in ("false", "0", "no", ""):
            return False, f"coerced str → bool ({value!r} → False)"
        # fall through to abort below

    try:
        coerced = py_type(value)
        return coerced, f"coerced {type(value).__name__} → {py_type.__name__} ({value!r} → {coerced!r})"
    except (ValueError, TypeError):
        return value, f"cannot coerce {value!r} to {target_type}"


# ── main entry ───────────────────────────────────────────────

def validate_and_repair(
    tool_input: dict[str, Any],
    schema: dict[str, dict] | None,
    handler: Callable | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """对 tool_input 进行校验和自动修复。

    Args:
        tool_input: LLM 生成的原始参数字典。
        schema: ToolRegistry 中的参数 schema（{name: {type, description}}）。
                为 None 时跳过修复（未知工具）。
        handler: 工具执行函数，用于提取默认值。为 None 时跳过默认值填充。

    Returns:
        (repaired_dict, warnings): warnings 为人类可读的修复/错误描述。
        修复失败时 returned dict 为空，warnings 包含错误信息。
    """
    if schema is None:
        return dict(tool_input), []

    repaired: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []

    # 提取 handler 默认值
    handler_defaults: dict[str, Any] = {}
    if handler is not None:
        try:
            sig = inspect.signature(handler)
            for pname, param in sig.parameters.items():
                if param.default is not inspect.Parameter.empty:
                    handler_defaults[pname] = param.default
        except (ValueError, TypeError):
            pass  # 无法 inspect 时跳过默认值填充

    # ── 1. 处理 tool_input 中存在的参数 ──
    for key, value in tool_input.items():
        if key not in schema:
            warnings.append(f"removed unknown param '{key}'")
            continue
        target_type = schema[key].get("type", "string")
        coerced, warn = _coerce(value, target_type)
        repaired[key] = coerced
        if warn:
            warnings.append(f"param '{key}': {warn}")

    # ── 2. 填充缺失参数 ──
    for key, info in schema.items():
        if key not in repaired:
            if key in handler_defaults:
                repaired[key] = handler_defaults[key]
                warnings.append(
                    f"param '{key}': filled default {handler_defaults[key]!r}"
                )
            else:
                errors.append(f"missing required param '{key}'")

    # ── 3. 校验必填参数值非空 ──
    for key, info in schema.items():
        if key not in repaired:
            continue
        target_type = info.get("type", "string")
        if target_type == "string" and isinstance(repaired[key], str) and repaired[key] == "":
            # 只在 schema 中没有 default 且 handler 也没有 default 时报错
            if key not in handler_defaults:
                errors.append(f"param '{key}': empty string for required param")
                break

    if errors:
        return {}, errors

    return repaired, warnings
```

- [ ] **Step 2: Verify import**

Run: `python -c "from agentd.tools.param_repair import validate_and_repair; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agentd/tools/param_repair.py
git commit -m "feat: add validate_and_repair() for tool call param repair"
```

archived-with: 2026-06-23-tool-call-param-repair
---

### Task 4: Modify `process_tool_call()` in runner.py

**Files:**
- Modify: `agentd/agent/runner.py:49-58`

**Interfaces:**
- Consumes: `self.container.tools_schemas` (from Task 2), `validate_and_repair` (from Task 3)
- Produces: (modified `process_tool_call` behavior — returns repaired or diagnostic results)

- [ ] **Step 1: Add import at top of file**

At line 1-13 in `agentd/agent/runner.py`, add:

```python
from agentd.tools.param_repair import validate_and_repair
```

Insert after existing imports (after line 12).

- [ ] **Step 2: Modify `process_tool_call()` method**

Replace lines 49-58:

```python
    # ── 工具调用 ──────────────────────────────────
    def process_tool_call(self, tool_name: str, tool_input: dict) -> str:
        handler = self.container.tools_handlers.get(tool_name)
        if handler is None:
            return f"Error: Unknown tool '{tool_name}'"

        # ── 参数校验 + 自动修复 ──
        schema = self.container.tools_schemas.get(tool_name)
        if schema:
            repaired, warnings = validate_and_repair(tool_input, schema, handler)
            for w in warnings:
                logger.warning("[param-repair] %s: %s (original=%s)", tool_name, w, repr(tool_input))
            if not repaired and warnings:
                return f"Error: Invalid arguments for {tool_name}: {'; '.join(warnings)}"
            tool_input = repaired

        # ── 安全网（repair 之后不太可能触发，但保留作为兜底）──
        try:
            return handler(**tool_input)
        except TypeError as exc:
            return f"Error: Invalid arguments for {tool_name}: {exc}"
        except Exception as exc:
            return f"Error: {tool_name} failed: {exc}"
```

- [ ] **Step 3: Verify existing behavior preserved**

Run: `pytest tests/ -x -q`
Expected: 68 passed (all existing tests)

- [ ] **Step 4: Commit**

```bash
git add agentd/agent/runner.py
git commit -m "feat: integrate param repair into process_tool_call"
```

archived-with: 2026-06-23-tool-call-param-repair
---

### Task 5: Write tests

**Files:**
- Create: `tests/test_param_repair.py`

**Interfaces:**
- Consumes: `validate_and_repair` from `agentd/tools/param_repair.py` (Task 3), `AgentRunner` from `agentd/agent/runner.py` (Task 4)
- Produces: (test coverage)

- [ ] **Step 1: Create test file**

```python
"""Tests for tool call parameter validation & auto-repair."""
import pytest
from agentd.tools.param_repair import validate_and_repair
from agentd.agent.runner import AgentRunner


# ── fixtures ──────────────────────────────────────────────

BASH_SCHEMA = {
    "command": {"type": "string", "description": "The shell command."},
    "timeout": {"type": "integer", "description": "Timeout in seconds."},
}

MEMORY_WRITE_SCHEMA = {
    "content": {"type": "string", "description": "The fact to remember."},
    "category": {"type": "string", "description": "Category."},
}

NO_PARAM_SCHEMA = {}


# ── type coercion ─────────────────────────────────────────

class TestTypeCoercion:
    def test_str_to_int(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": "30"}, BASH_SCHEMA
        )
        assert repaired["timeout"] == 30
        assert any("coerced" in w for w in warnings)

    def test_int_to_str(self):
        schema = {"command": {"type": "string"}}
        repaired, warnings = validate_and_repair({"command": 42}, schema)
        assert repaired["command"] == "42"
        assert any("coerced" in w for w in warnings)

    def test_float_to_int(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": 3.7}, BASH_SCHEMA
        )
        assert repaired["timeout"] == 3
        assert any("coerced" in w for w in warnings)

    def test_already_correct_type_no_warning(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": 30}, BASH_SCHEMA
        )
        assert repaired == {"command": "ls", "timeout": 30}
        assert warnings == []

    def test_bool_str_coercion(self):
        schema = {"verbose": {"type": "boolean"}}
        repaired, warnings = validate_and_repair({"verbose": "true"}, schema)
        assert repaired["verbose"] is True

        repaired, _ = validate_and_repair({"verbose": "false"}, schema)
        assert repaired["verbose"] is False

    def test_coercion_failure_reports_error(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": "abc"}, BASH_SCHEMA
        )
        assert repaired == {}
        assert any("cannot coerce" in w for w in warnings)


# ── extra param removal ───────────────────────────────────

class TestExtraParamRemoval:
    def test_extra_param_removed(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "hallucinated": "x"}, BASH_SCHEMA
        )
        assert "hallucinated" not in repaired
        assert "command" in repaired
        assert any("unknown param" in w for w in warnings)


# ── default value filling ─────────────────────────────────

def _dummy_handler(command, timeout=30):
    pass

def _dummy_no_defaults(command, timeout):
    pass


class TestDefaultFilling:
    def test_missing_optional_filled(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls"}, BASH_SCHEMA, _dummy_handler
        )
        assert repaired["timeout"] == 30
        assert any("filled default" in w for w in warnings)

    def test_missing_required_reports_error(self):
        repaired, warnings = validate_and_repair(
            {}, BASH_SCHEMA, _dummy_no_defaults
        )
        assert repaired == {}
        assert any("missing required" in w for w in warnings)

    def test_multiple_missing_required(self):
        repaired, warnings = validate_and_repair(
            {}, BASH_SCHEMA, _dummy_no_defaults
        )
        assert len(warnings) >= 2
        assert all("missing required" in w for w in warnings)

    def test_fill_only_defaults_not_required(self):
        """有默认值的填，无默认值的不填但也不报错（因为 tool_input 提供了）"""
        repaired, warnings = validate_and_repair(
            {"command": "ls"}, BASH_SCHEMA, _dummy_handler
        )
        assert repaired["command"] == "ls"
        assert repaired["timeout"] == 30


# ── empty input / no-param tools ──────────────────────────

class TestEdgeCases:
    def test_empty_input_all_defaults(self):
        """没有必填参数的工具，空输入应该全部填默认值。"""
        def handler(verbose=False, timeout=10):
            pass
        schema = {
            "verbose": {"type": "boolean"},
            "timeout": {"type": "integer"},
        }
        repaired, warnings = validate_and_repair({}, schema, handler)
        assert repaired == {"verbose": False, "timeout": 10}

    def test_no_param_tool(self):
        """get_current_time 等无参数工具。"""
        repaired, warnings = validate_and_repair({}, NO_PARAM_SCHEMA)
        assert repaired == {}
        assert warnings == []

    def test_none_schema_passthrough(self):
        """未知工具的 schema 为 None，直接透传。"""
        repaired, warnings = validate_and_repair(
            {"any": "thing"}, None
        )
        assert repaired == {"any": "thing"}
        assert warnings == []

    def test_multiple_issues(self):
        """同时有类型错误、多余参数、缺失默认值。"""
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": "5.0", "extra": "x"}, BASH_SCHEMA, _dummy_handler
        )
        assert repaired["timeout"] == 5
        assert "extra" not in repaired
        assert "command" in repaired
        assert len(warnings) >= 2  # coercion + extra removal


# ── integration: process_tool_call ─────────────────────────

class TestProcessToolCallIntegration:
    """端到端：用 malformed input 调用真实的 process_tool_call。"""

    def test_repaired_bash_timeout(self):
        runner = AgentRunner("test")
        result = runner.process_tool_call("bash", {"command": "echo hi", "timeout": "5"})
        assert "hi" in result
        assert "Error" not in result

    def test_missing_required_command(self):
        runner = AgentRunner("test")
        result = runner.process_tool_call("bash", {})
        assert "Error" in result
        assert "command" in result.lower()

    def test_unknown_tool(self):
        runner = AgentRunner("test")
        result = runner.process_tool_call("nonexistent", {})
        assert "Unknown tool" in result

    def test_get_current_time_no_params(self):
        runner = AgentRunner("test")
        result = runner.process_tool_call("get_current_time", {})
        assert "Error" not in result
        assert "UTC" in result
```

- [ ] **Step 2: Run tests — expect some to fail (no integration test isolation yet)**

Run: `pytest tests/test_param_repair.py -v`
Expected: ~12 unit tests pass, integration tests may need runner context

- [ ] **Step 3: Run full regression**

Run: `pytest tests/ -x -q`
Expected: 68 + ~12 = ~80 passed

- [ ] **Step 4: Commit**

```bash
git add tests/test_param_repair.py
git commit -m "test: add param repair unit + integration tests"
```

archived-with: 2026-06-23-tool-call-param-repair
---

### Task 6: Update tasks.md checkboxes

- [ ] **Step 1: Mark all tasks complete in tasks.md**

Update `openspec/changes/tool-call-param-repair/tasks.md` — change all `- [ ]` to `- [x]`.

- [ ] **Step 2: Final test run**

Run: `pytest tests/ -v`
Expected: all tests pass (~80)

- [ ] **Step 3: Commit**

```bash
git add openspec/changes/tool-call-param-repair/tasks.md
git commit -m "chore: mark tasks complete for tool-call-param-repair"
```
