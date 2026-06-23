# Comet Design Handoff

- Change: tool-call-param-repair
- Phase: design
- Mode: compact
- Context hash: be40d63b552b436a95621a2aa95bad72c8c50ac49b1e211e229097729d82c023

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/tool-call-param-repair/proposal.md

- Source: openspec/changes/tool-call-param-repair/proposal.md
- Lines: 1-35
- SHA256: 79ddce19f58c751dbe8fcc35ec52e400a90f243dee8dfd2e0d41cd279d43b348

```md
# Proposal: Tool Call Parameter Validation & Auto-Repair

## Problem

When an LLM generates a tool call with malformed JSON parameters, `AgentRunner.process_tool_call()` calls `handler(**tool_input)` directly. Malformed input causes a `TypeError` that is caught and returned as an opaque error string to the model — the conversation degrades because the model can't see _which_ parameter was wrong or _how_ to fix it.

Common LLM parameter errors:
- **Type mismatch**: `timeout: "30"` (string instead of integer)
- **Extra parameters**: hallucinated fields not in the tool schema
- **Missing optional parameters**: omitting defaults like `timeout`, `category`
- **Missing required parameters**: no `command` for `bash` tool

## Goal

Add a **validation and auto-repair layer** in `process_tool_call()` that, before calling the handler:

1. Compares `tool_input` against the registered tool schema (from `ToolRegistry`)
2. Attempts automatic repair: type coercion, removing extra params, filling defaults
3. Returns a **diagnostic error** (not a raw Python traceback) when repair is impossible
4. Logs repairs so operators can detect LLM prompt quality issues

## Scope

- **In**: `agentd/agent/runner.py` — `process_tool_call()` method
- **In**: New module `agentd/tools/param_repair.py` — validation/repair logic
- **In**: Tests for repair strategies and edge cases
- **Out**: LLM prompt changes (separate concern)
- **Out**: Tool schema changes (existing schemas are sufficient)

## Success Criteria

1. Malformed tool calls are auto-repaired whenever possible (type coercion, extra param removal, default filling)
2. Unrepairable calls return diagnostic messages naming the specific parameter and problem
3. Repaired calls are logged at WARNING level for observability
4. All existing tests continue to pass
```

## openspec/changes/tool-call-param-repair/design.md

- Source: openspec/changes/tool-call-param-repair/design.md
- Lines: 1-78
- SHA256: f2ccc456dfe9f6b2128fd77101f80d06e3e7e6a60afabec9509f38c1faa9bb97

```md
# Design: Tool Call Parameter Validation & Auto-Repair

## Architecture

```
process_tool_call(name, input)
  │
  ├─ 1. Lookup handler + schema in ToolRegistry
  │     unknown tool → "Error: Unknown tool '{name}'"
  │
  ├─ 2. validate_and_repair(input, schema, handler)
  │     │
  │     ├─ Coerce types (schema-driven): "30" → 30, 42 → "42"
  │     ├─ Remove extra keys not in schema
  │     ├─ Fill missing optional params from handler defaults (inspect.signature)
  │     ├─ Check required params present after repair
  │     └─ Return (repaired_input, warnings[])
  │
  ├─ 3. Log any warnings at WARNING level
  │
  └─ 4. handler(**repaired_input)
```

## Key Decisions

### D1: Schema-driven repair (not handler-signature-driven)

Tool schemas in `ToolRegistry` declare `type` per parameter (`"string"`, `"integer"`). Use these as the authoritative source for type coercion — more reliable than Python type hints which can be `Union`, `Optional`, or missing.

### D2: Handler defaults via `inspect.signature`

For filling missing optional parameters, use `inspect.signature(handler)` to extract default values. This ensures the repair layer stays in sync with the actual function signatures without manual duplication.

### D3: Repair, don't hallucinate

Only fill defaults that the handler explicitly provides. Never invent values for missing required parameters — return a diagnostic error instead.

### D4: Log repairs at WARNING

Every repair is a signal that the LLM prompt or model behavior may need tuning. Log at `WARNING` so operators can aggregate repair frequency per tool.

## Repair Strategies

| Condition | Strategy | Example |
|-----------|----------|---------|
| `str` where `int` expected | `int()` cast | `"30"` → `30` |
| `int` where `str` expected | `str()` cast | `42` → `"42"` |
| `float` where `int` expected | `int()` truncate | `3.7` → `3` |
| Extra key not in schema | Remove | `{cmd, extra}` → `{cmd}` |
| Missing optional param | Fill from handler default | `{}` → `{timeout: 30}` for bash |
| Missing required param | **Fail** with diagnostic | `No 'command' param for bash` |

## Non-Repairs (return diagnostic error)

- Missing required parameter
- Type mismatch that can't be coerced (e.g., `timeout: "abc"` → int fails)
- Empty required string parameter

## Data Flow

```
ToolRegistry.register()
  └─ stores: {name} → {parameters: {param: {type, description}}, handler}
                                  │                    │
                                  ▼                    ▼
                         schema-driven          inspect.signature
                         type coercion          default extraction
                                  │                    │
                                  └────────┬───────────┘
                                           ▼
                                  validate_and_repair()
```

## Error Handling

- Repair failures: `return "Error: Invalid arguments for {tool}: {specific diagnostic}"`
- The existing `try/except TypeError` in `process_tool_call` becomes a safety net (should rarely trigger after repair)
- Generic `except Exception` remains as final fallback
```

## openspec/changes/tool-call-param-repair/tasks.md

- Source: openspec/changes/tool-call-param-repair/tasks.md
- Lines: 1-38
- SHA256: 306a569d7b2ca509d3fa91d969dacdd572698839b90a3d5d6ecd9131e501b1fd

```md
# Tasks: Tool Call Parameter Validation & Auto-Repair

## Task 1: Create `agentd/tools/param_repair.py` — validation/repair module

- [ ] Implement `validate_and_repair(tool_input, schema, handler) → (dict, list[str])`
  - Type coercion based on schema `parameters[param].type`
  - Remove extra keys not in schema
  - Fill missing optional params from `inspect.signature(handler)` defaults
  - Return repaired dict + list of warning strings
- [ ] Implement `repair_possible(tool_input, schema) → bool` — check if all required params present (with defaults considered)

## Task 2: Modify `process_tool_call()` in `agentd/agent/runner.py`

- [ ] Look up parameter schema from `ToolRegistry` (expose via container or registry)
- [ ] Call `validate_and_repair()` before `handler(**tool_input)`
- [ ] Log warnings at `WARNING` level
- [ ] Return diagnostic error when repair impossible
- [ ] Keep existing `try/except` as safety net

## Task 3: Expose tool parameter schema

- [ ] Add `get_tool_schema(name)` or equivalent to `ToolRegistry` or `Container`
- [ ] Ensure `process_tool_call` can access the schema for the given tool name

## Task 4: Write tests

- [ ] `tests/test_param_repair.py` — unit tests for repair strategies:
  - Type coercion: str→int, int→str, float→int
  - Extra param removal
  - Missing optional param filled from default
  - Missing required param → repair impossible
  - Empty input, already-valid input (no-op)
  - Multiple errors in one input
- [ ] Regression: all 68 existing tests pass

## Task 5: Integration test

- [ ] Test `process_tool_call` end-to-end with malformed input for a real tool (e.g., `bash` with `timeout: "10"`)
```

