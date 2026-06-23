# Tasks: Tool Call Parameter Validation & Auto-Repair

## Task 1: Add `get_tool_schema()` to ToolRegistry

- [x] Add `get_tool_schema(name) -> dict | None` method to `ToolRegistry` (7 lines)

## Task 2: Add `tools_schemas` property to Container

- [x] Add `tools_schemas` property that derives `{name: {param: {type, description}}}` from `self.tools`

## Task 3: Create `agentd/tools/param_repair.py` — validation/repair module

- [x] Implement `validate_and_repair(tool_input, schema, handler) → (dict, list[str])`
  - [x] Type coercion based on schema `parameters[param].type` (str↔int, float→int, bool)
  - [x] Remove extra keys not in schema
  - [x] Fill missing optional params from `inspect.signature(handler)` defaults
  - [x] Return repaired dict + list of warning/error strings
  - [x] Coercion failures treated as hard errors (returns `{}, errors`)

## Task 4: Modify `process_tool_call()` in `agentd/agent/runner.py`

- [x] Import `validate_and_repair` from `agentd.tools.param_repair`
- [x] Look up parameter schema from `self.container.tools_schemas`
- [x] Call `validate_and_repair()` before `handler(**tool_input)`
- [x] Log warnings at `WARNING` level
- [x] Return diagnostic error when repair impossible
- [x] Keep existing `try/except TypeError` and `except Exception` as safety net

## Task 5: Write tests

- [x] `tests/test_param_repair.py` — 25 tests:
  - [x] Type coercion: str→int, int→str, float→int, bool, bool→int
  - [x] Extra param removal
  - [x] Missing optional param filled from default
  - [x] Missing required param → error
  - [x] Coercion failure → error
  - [x] Empty input, already-valid input (no-op)
  - [x] Multiple issues in one input
  - [x] None schema passthrough, unknown type passthrough
  - [x] handler=None skips defaults
  - [x] Integration: process_tool_call end-to-end (bash, memory_write, get_current_time)
- [x] Regression: 68 + 25 = 93 tests passing
