from utils.print_tools import print_tool
from typing import Any


def tool_skill_invoke(name: str, args: str = "") -> str:
    """按需加载指定技能模块，返回完整操作指令正文。"""
    from agentd.bootstrap import get_current_container

    print_tool("skill_invoke", name)
    skills_mgr = get_current_container().get("skills_mgr")

    skill = skills_mgr.get_skill(name)
    if skill is None:
        available = [s["name"] for s in skills_mgr.skills]
        avail_list = ", ".join(available) if available else "(无可用技能)"
        return f"Unknown skill: '{name}'. Available: {avail_list}"

    body = skill.get("body", "")
    if not body:
        return f"Skill '{name}' 已加载，但正文为空。"

    return body


# ---------------------------------------------------------------------------
# 工具定义: Schema + Handler
# ---------------------------------------------------------------------------

from agentd.tools.registry import registry

registry.register(
    name="skill_invoke",
    description=(
        "加载一个已注册的技能模块，获取其完整操作指令。"
        "加载后，你必须严格按照技能指令执行——技能定义的是操作流程，不是参考建议。"
        "可用技能列表见系统提示词中的技能注册表。"
    ),
    parameters={
        "name": {"type": "string", "description": "要加载的技能名称"},
        "args": {"type": "string", "description": "传递给技能的可选参数"},
    },
    handler=tool_skill_invoke,
    toolset="skill",
)

# 向后兼容
TOOLS = [t for t in registry.get_tools() if t["name"] == "skill_invoke"]
TOOL_HANDLERS: dict[str, Any] = {
    "skill_invoke": tool_skill_invoke,
}
