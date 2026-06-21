"""工具汇总入口 — import 触发各工具模块自注册到 ToolRegistry。"""

# 导入即注册（利用 Python 模块加载副作用）
from agentd.tools import memory_tools   # noqa: F401
from agentd.tools import file_tools     # noqa: F401
from agentd.tools import browser_tools  # noqa: F401
from agentd.tools import skill_tools    # noqa: F401

from agentd.tools.registry import registry


def get_tools():
    return registry.get_tools()


def get_tool_handlers():
    return registry.get_handlers()


# 向后兼容的模块级变量
TOOLS = get_tools()
TOOL_HANDLERS = get_tool_handlers()
