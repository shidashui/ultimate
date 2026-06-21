# Tasks: Fix tools_handlers None Init

- [x] **Task 1**: Replace `TOOLS`/`TOOL_HANDLERS` module variables with `get_tools()`/`get_tool_handlers()` calls in `container.py`
- [x] **Task 2**: Verify `python -c "from agentd.bootstrap.container import container"` — 12 tools, 12 handlers, all populated
