"""工具汇总入口 — import 触发各工具模块自注册到 ToolRegistry。"""


def get_tools():
    # 惰性导入触发各工具模块自注册到 registry
    from agentd.tools import memory_tools   # noqa: F401
    from agentd.tools import file_tools     # noqa: F401
    from agentd.tools import browser_tools  # noqa: F401
    from agentd.tools import skill_tools    # noqa: F401
    from agentd.tools.registry import registry
    return registry.get_tools()


def get_tool_handlers():
    # 惰性导入触发各工具模块自注册到 registry
    from agentd.tools import memory_tools   # noqa: F401
    from agentd.tools import file_tools     # noqa: F401
    from agentd.tools import browser_tools  # noqa: F401
    from agentd.tools import skill_tools    # noqa: F401
    from agentd.tools.registry import registry
    return registry.get_handlers()


# 向后兼容的模块级变量（惰性求值，避免循环导入）
TOOLS = None
TOOL_HANDLERS = None


def _init():
    global TOOLS, TOOL_HANDLERS
    if TOOLS is None:
        TOOLS = get_tools()
        TOOL_HANDLERS = get_tool_handlers()
