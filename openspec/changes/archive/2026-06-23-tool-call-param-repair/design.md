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
