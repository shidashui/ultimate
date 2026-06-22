## Context

当前项目使用 Claude Code skill 系统（`.claude/skills/<name>/SKILL.md`）来组织可复用的工作流程和参考指南。已有 30+ 生产 skill，但缺少轻量级测试 skill 来验证 skill 调用机制。

## Goals / Non-Goals

**Goals:**
- 创建 3 个最小化 skill 用于测试不同维度的 skill 功能
- 每个 skill 独立、无依赖、可被 `/` 命令和 Skill 工具调用

**Non-Goals:**
- 不引入任何框架或测试基础设施
- 不修改现有 skill 或项目代码
- 不涉及 CI/CD 集成

## Decisions

| 决策 | 选型 | 理由 |
|------|------|------|
| Skill 粒度 | 每个 skill 一个 SKILL.md | 保持最小化，聚焦单一测试维度 |
| 命名风格 | `test-<维度>` kebab-case | 与现有 skill 命名一致，易于识别 |
| 目录位置 | `workspace/skills/` | 项目 SkillsManager 自动扫描路径 |
| 参数传递 | SKILL.md 中定义 args 占位符 | 测试 Agent 工具的参数注入机制 |

### Skill 设计

1. **hello-skill** — 最简 skill，仅 frontmatter + 一句话回复
2. **echo-args** — 接收 args 并回显在输出中
3. **system-info** — 包含可执行的 Bash 命令步骤

## Risks / Trade-offs

- **测试 skill 被误用于生产** → 命名以 `test-` 前缀区分，避免歧义
- **skill 内容过于简单** → 这正是测试目的 — 验证最小可工作 skill
