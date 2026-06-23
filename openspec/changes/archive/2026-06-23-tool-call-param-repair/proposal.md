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
