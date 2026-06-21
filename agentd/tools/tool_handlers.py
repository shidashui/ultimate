

def get_tools():
    from agentd.tools.memory_tools import TOOLS as MEMORY_TOOLS
    from agentd.tools.file_tools import TOOLS as FILE_TOOLS
    from agentd.tools.browser_tools import TOOLS as BROWSER_TOOLS
    from agentd.tools.skill_tools import TOOLS as SKILL_TOOLS

    return MEMORY_TOOLS + FILE_TOOLS + BROWSER_TOOLS + SKILL_TOOLS

def get_tool_handlers():
    from agentd.tools.memory_tools import TOOL_HANDLERS as MEMORY_TOOL_HANDLERS
    from agentd.tools.file_tools import TOOL_HANDLERS as FILE_TOOL_HANDLERS
    from agentd.tools.browser_tools import TOOL_HANDLERS as BROWSER_TOOL_HANDLERS
    from agentd.tools.skill_tools import TOOL_HANDLERS as SKILL_TOOL_HANDLERS

    return {**MEMORY_TOOL_HANDLERS, **FILE_TOOL_HANDLERS, **BROWSER_TOOL_HANDLERS, **SKILL_TOOL_HANDLERS}

TOOLS = get_tools()
TOOL_HANDLERS = get_tool_handlers()