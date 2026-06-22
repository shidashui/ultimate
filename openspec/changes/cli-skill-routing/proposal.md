# Proposal: CLI Skill Routing

## 问题

用户在 REPL 中键入 `/技能名` 时，CLI 无法识别技能命令，输入被当作普通消息发送给 AI。虽然 AI 可能在 system prompt 中看到技能注册信息后自行调用 `skill_invoke` 工具，但这依赖 AI 的理解能力，存在以下问题：

1. **无即时反馈** — 用户键入 `/comet` 后没有"技能已触发"的确认，体验模糊
2. **Tab 补全缺失** — `WordCompleter` 硬编码了 14 个 REPL 命令，技能名（如 `/comet`、`/brainstorming`）不在补全列表中
3. **路由不透明** — 技能调用路径（REPL → AI → skill_invoke 工具）冗长且不可见

## 目标

让用户通过 `/技能名` 在 REPL 中直接调用 skill，技能 body 作为上下文注入 AI 调用，提供明确的路由反馈。

## 范围

**In scope:**
- 动态 Tab 补全：从 `SkillsManager.skills` 读取 `invocation` 字段，合并到 `WordCompleter`
- 技能路由：`handle_repl_command` 中匹配 `/技能名`，加载 skill body，注入 AI 消息上下文
- 帮助集成：`/help` 自动列出可用技能

**Out of scope:**
- Skill 参数解析（保持当前 `/技能名 <自由文本>` 透传）
- Skill 嵌套调用
- Skill 热加载

## 成功标准

- 用户键入 `/com` + Tab → 自动补全为 `/comet`
- 用户键入 `/comet 美化cli` → 控制台显示"技能已触发: comet"，skill body 注入 AI 上下文
- `/help` 输出包含所有可用技能
