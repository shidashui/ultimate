# Proposal: Fix tools_handlers None Init

## Problem

`python ultimate.py chat` crashes at startup with:

```
AttributeError: 'NoneType' object has no attribute 'keys'
at cli/cli.py:36: self.runner.container.tools_handlers.keys()
```

## Root Cause

In the `hermes-agent-refactor` change, `agentd/tools/tool_handlers.py` was refactored to use lazy imports. The backward-compat module-level variables `TOOLS` and `TOOL_HANDLERS` were changed from direct values to `None`, with a new `_init()` function to populate them. However, `_init()` is **never called**.

Import chain:
1. `cli.py` → `AgentRunner` → `container.py`
2. `container.py:7` → `from agentd.tools.tool_handlers import TOOLS, TOOL_HANDLERS`
3. `TOOLS = None`, `TOOL_HANDLERS = None` (module level)
4. `_init()` exists but is never invoked
5. `container.py:36-37`: `self.tools = None`, `self.tools_handlers = None`
6. `cli.py:36`: `.keys()` on `None` → crash

## Fix

Call `_init()` in `container.py` before using `TOOLS`/`TOOL_HANDLERS`. This is a 2-line change in 1 file.

## Scope

- **In scope**: Ensure `_init()` populates backward-compat module variables before use
- **Out of scope**: Other import refactoring, additional lazy loading changes
