from pathlib import Path
from config.configs import WORKSPACE_DIR, MAX_SKILLS, MAX_SKILLS_PROMPT

# ---------------------------------------------------------------------------
# 3. 技能发现与注入
# ---------------------------------------------------------------------------
# 一个技能 = 一个包含 SKILL.md (带 frontmatter) 的目录.
# 按优先级顺序扫描; 同名技能会被后发现的覆盖.


class SkillsManager:

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir
        self.skills: list[dict[str, str]] = []

    def _parse_frontmatter(self, text: str) -> dict[str, str]:
        """解析简单的 YAML frontmatter, 不依赖 pyyaml."""
        meta: dict[str, str] = {}
        if not text.startswith("---"):
            return meta
        parts = text.split("---", 2)
        if len(parts) < 3:
            return meta
        for line in parts[1].strip().splitlines():
            if ":" not in line:
                continue
            key, _, value = line.strip().partition(":")
            meta[key.strip()] = value.strip()
        return meta

    def _scan_dir(self, base: Path) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        if not base.is_dir():
            return found
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                content = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue
            meta = self._parse_frontmatter(content)
            if not meta.get("name"):
                continue
            body = ""
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2].strip()
            found.append({
                "name": meta.get("name", ""),
                "description": meta.get("description", ""),
                "invocation": meta.get("invocation", ""),
                "body": body,
                "path": str(child),
            })
        return found

    def discover(self, extra_dirs: list[Path] | None = None) -> None:
        """按优先级扫描技能目录; 同名技能后者覆盖前者."""
        scan_order: list[Path] = []
        if extra_dirs:
            scan_order.extend(extra_dirs)
        scan_order.append(self.workspace_dir / "skills")           # 内置技能
        scan_order.append(self.workspace_dir / ".skills")          # 托管技能
        scan_order.append(self.workspace_dir / ".agents" / "skills")  # 个人 agent 技能
        scan_order.append(Path.cwd() / ".agents" / "skills")      # 项目 agent 技能
        scan_order.append(Path.cwd() / "skills")                  # 工作区技能

        seen: dict[str, dict[str, str]] = {}
        for d in scan_order:
            for skill in self._scan_dir(d):
                seen[skill["name"]] = skill
        self.skills = list(seen.values())[:MAX_SKILLS]

    # ── 运行时 skill 调度 ──────────────────────────
    def get_skill(self, name: str) -> dict | None:
        """按名称查找 skill，返回完整信息字典或 None。"""
        for s in self.skills:
            if s["name"] == name:
                return s
        return None

    def build_skill_invoke_tool(self) -> dict:
        """生成 skill_invoke 工具 schema，description 含动态 skill 列表。"""
        if self.skills:
            entries = [f"- {s['name']}: {s['description']}" for s in self.skills]
            registry_text = "\n".join(entries)
        else:
            registry_text = "(无可用技能)"

        return {
            "name": "skill_invoke",
            "description": (
                "加载一个已注册的技能模块，获取其完整操作指令。"
                "加载后，你必须严格按照技能指令执行——技能定义的是操作流程，不是参考建议。"
                "当前可用技能:\n" + registry_text
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名称，必须是上述可用技能之一",
                    },
                    "args": {
                        "type": "string",
                        "description": "传递给技能的可选参数",
                    },
                },
                "required": ["name"],
            },
        }

    def format_skill_registry(self) -> str:
        """生成轻量技能注册表（仅名称 + 描述），用于 system prompt 注入。"""
        if not self.skills:
            return "(无可用技能)"
        lines = ["| 技能 | 描述 |", "|------|------|"]
        for s in self.skills:
            lines.append(f"| {s['name']} | {s['description']} |")
        return "\n".join(lines)

    def format_prompt_block(self) -> str:
        if not self.skills:
            return ""
        lines = ["## Available Skills", ""]
        total = 0
        for skill in self.skills:
            block = (
                f"### Skill: {skill['name']}\n"
                f"Description: {skill['description']}\n"
                f"Invocation: {skill['invocation']}\n"
            )
            if skill.get("body"):
                block += f"\n{skill['body']}\n"
            block += "\n"
            if total + len(block) > MAX_SKILLS_PROMPT:
                lines.append(f"(... more skills truncated)")
                break
            lines.append(block)
            total += len(block)
        return "\n".join(lines)
