from datetime import datetime, timezone
from config.configs import MODEL

SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to tools.\n"
    "Use tools to help the user with file and time queries.\n"
    "Be concise. If a session has prior context, use it."
)


# ---------------------------------------------------------------------------
# 5. 系统提示词组装 -- 核心函数
# ---------------------------------------------------------------------------
# 教学演示 8 个关键提示词层级.
# 每轮重建 -- 上一轮可能更新了记忆.
# 模式: full (主 agent) / minimal (子 agent / cron) / none (最小化)


def build_system_prompt(
    mode: str = "full",
    bootstrap: dict[str, str] | None = None,
    skill_registry: str = "",
    memory_context: str = "",
    agent_id: str = "main",
    channel: str = "terminal",
) -> str:
    if bootstrap is None:
        bootstrap = {}
    sections: list[str] = []

    # 第 1 层: 身份 -- 来自 IDENTITY.md 或默认值
    identity = bootstrap.get("IDENTITY.md", "").strip()
    sections.append(identity if identity else "You are a helpful personal AI assistant.")

    # 第 1.5 层: Skill 执行协议 -- 元指令
    sections.append(
        "## Skill Execution Protocol\n\n"
        "When a skill is loaded via skill_invoke, its instructions are "
        "authoritative. You MUST follow the skill's defined process exactly. "
        "Skill instructions override conflicting default behaviors."
    )

    # 第 2 层: 灵魂 -- 人格注入, 越靠前影响力越强
    if mode == "full":
        soul = bootstrap.get("SOUL.md", "").strip()
        if soul:
            sections.append(f"## Personality\n\n{soul}")

    # 第 3 层: 工具使用指南
    tools_md = bootstrap.get("TOOLS.md", "").strip()
    if tools_md:
        sections.append(f"## Tool Usage Guidelines\n\n{tools_md}")

    # 第 4 层: 技能注册表 -- 名称 + 描述，完整正文通过 skill_invoke 按需加载
    if mode == "full" and skill_registry:
        sections.append(
            "## Available Skills\n\n"
            "向模型声明可用的技能模块。每个技能可通过 `skill_invoke` 工具按需加载。\n\n"
            f"{skill_registry}"
        )

    # 第 5 层: 记忆 -- 长期记忆引用，自动召回内容注入 user message
    if mode == "full":
        mem_md = bootstrap.get("MEMORY.md", "").strip()
        if mem_md:
            sections.append(f"## Memory\n\n### Evergreen Memory\n\n{mem_md}")
        sections.append(
            "## Memory Instructions\n\n"
            "- Use memory_write to save important user facts and preferences.\n"
            "- Reference remembered facts naturally in conversation.\n"
            "- Use memory_search to recall specific past information."
        )

    # 第 6 层: Bootstrap 上下文 -- 剩余的 Bootstrap 文件
    if mode in ("full", "minimal"):
        for name in ["HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "USER.md"]:
            content = bootstrap.get(name, "").strip()
            if content:
                sections.append(f"## {name.replace('.md', '')}\n\n{content}")

    # 第 7 层: 运行时上下文（时间戳移入 user message 每轮动态注入）
    sections.append(
        f"## Runtime Context\n\n"
        f"- Agent ID: {agent_id}\n- Model: {MODEL['name']}\n"
        f"- Channel: {channel}\n- Prompt mode: {mode}"
    )

    # 第 8 层: 渠道提示
    hints = {
        "terminal":  "You are responding via a terminal REPL. Markdown is supported.",
        "telegram":  "You are responding via Telegram. Keep messages concise.",
        "discord":   "You are responding via Discord. Keep messages under 2000 characters.",
        "slack":     "You are responding via Slack. Use Slack mrkdwn formatting.",
        "wechat":    "You are responding via WeChat. Keep messages concise, avoid Markdown, use plain text only.",
    }
    sections.append(f"## Channel\n\n{hints.get(channel, f'You are responding via {channel}.')}")

    return "\n\n".join(sections)