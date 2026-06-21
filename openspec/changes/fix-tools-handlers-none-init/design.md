# Design: Fix tools_handlers None Init

## Approach

**Call `_init()` from `container.py` after import**, before `TOOLS`/`TOOL_HANDLERS` are assigned to `self.tools`/`self.tools_handlers`.

### Change (agentd/bootstrap/container.py)

```python
# Before:
from agentd.tools.tool_handlers import TOOLS, TOOL_HANDLERS

# After:
from agentd.tools.tool_handlers import TOOLS, TOOL_HANDLERS, _init
_init()
```

The `_init()` call populates the global `TOOLS` and `TOOL_HANDLERS` module variables with actual values from the registry, so `container.py` gets valid dicts.

### Why not call _init() at bottom of tool_handlers.py?

That would trigger all lazy imports at module load time, undermining the lazy import pattern used to avoid circular dependencies. Calling `_init()` explicitly in the consumer (`container.py`) preserves the lazy semantics for other consumers.

### Why not use get_tools()/get_tool_handlers() directly?

Possible but 2-line change achieves the same result with less diff. The backward-compat module variables exist to support `container.py`'s existing import style.

## Risk

- **Circular import**: The tool files imported by `_init()` (memory_tools, file_tools, etc.) no longer import `container` at module level (fixed in `hermes-agent-refactor`). Safe.
