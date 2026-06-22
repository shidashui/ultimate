# Comet Design Handoff

- Change: create-test-skills
- Phase: design
- Mode: compact
- Context hash: 7fde2008abad70baab6fe4667cfe881f4726c3b968bcd92301bb68db7341aaac

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/create-test-skills/proposal.md

- Source: openspec/changes/create-test-skills/proposal.md
- Lines: 1-28
- SHA256: 7f0878776dbe9c1d71cec509822d4b520554bd25701dc4c92443f8f0551dc12e

```md
## Why

当前项目已有大量 skill（comet 系列、openspec 系列、superpowers 系列），但这些 skill 都是生产级别的复杂文档。当开发新功能或调试时，缺少轻量级测试 skill 来验证 Claude Code 的 skill 调用机制（Skill 工具、/slash 命令、自动匹配等）是否正常工作。

创建几个简单的测试 skill，方便在任何修改后快速验证 skill 系统功能。

## What Changes

- 创建 3 个轻量级测试 skill：
  1. **hello-skill**：最简单的 skill，仅输出问候语，验证基本 skill 调用
  2. **echo-args**：接收参数并回显，验证 skill 参数传递机制
  3. **system-info**：输出当前系统环境信息，验证 skill 可执行 shell 命令
- 每个 skill 仅包含一个 `SKILL.md` 文件，无额外依赖

## Capabilities

### New Capabilities
- `test-skills`: 轻量级测试 skill 集合，用于验证 Claude Code skill 调用机制

### Modified Capabilities

（无）

## Impact

- 仅新增 `workspace/skills/` 下的 3 个目录和文件
- 不影响任何现有代码或功能
- 不影响现有 skill 的行为
```

## openspec/changes/create-test-skills/design.md

- Source: openspec/changes/create-test-skills/design.md
- Lines: 1-34
- SHA256: 2cc3142a2aa3dcd26c75cc607b62bb48ca9e66ffd4fc3e551d6bd9733e508092

```md
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
```

## openspec/changes/create-test-skills/tasks.md

- Source: openspec/changes/create-test-skills/tasks.md
- Lines: 1-11
- SHA256: 5c464ab124fb78875389a9ffc41992380318c4e8bcb23e2165c10dad3e58184c

```md
## 1. hello-skill

- [ ] 1.1 创建 `workspace/skills/hello-skill/SKILL.md`，包含 frontmatter 和问候输出

## 2. echo-args

- [ ] 2.1 创建 `workspace/skills/echo-args/SKILL.md`，接收 args 参数并回显

## 3. system-info

- [ ] 3.1 创建 `workspace/skills/system-info/SKILL.md`，包含 Bash 命令查看系统环境信息
```

## openspec/changes/create-test-skills/specs/test-skills/spec.md

- Source: openspec/changes/create-test-skills/specs/test-skills/spec.md
- Lines: 1-34
- SHA256: 56a66cd01a891616574da2db2303ded78864788df50b5d93f8ee276e9cb934d7

```md
## ADDED Requirements

### Requirement: hello-skill 可通过 /hello-skill 调用
系统 SHALL 提供 `hello-skill`，用户可通过 `/hello-skill` 命令调用。当调用时，skill SHALL 输出一句问候语并告知调用方式。

#### Scenario: 调用 /hello-skill 返回问候
- **WHEN** 用户输入 `/hello-skill`
- **THEN** skill 输出问候语，包含 "Hello" 字样

#### Scenario: 通过 Skill 工具调用返回相同结果
- **WHEN** Skill 工具以 skill="hello-skill" 调用
- **THEN** 输出与直接 `/hello-skill` 相同

### Requirement: echo-args 可接收并回显参数
系统 SHALL 提供 `echo-args`，接收用户传入的 args 并原样回显。

#### Scenario: 传递参数被回显
- **WHEN** 用户输入 `/echo-args 测试消息`
- **THEN** skill 输出中包含 "测试消息" 或直接回显 args

#### Scenario: 无参数时不报错
- **WHEN** 用户输入 `/echo-args`（无参数）
- **THEN** skill 不报错，输出提示 "No args provided"

### Requirement: system-info 可执行命令输出环境信息
系统 SHALL 提供 `system-info`，可执行 Bash 命令输出当前系统环境信息。

#### Scenario: 调用显示系统信息
- **WHEN** 用户输入 `/system-info`
- **THEN** skill 执行系统命令并输出结果（如当前目录、时间等）

#### Scenario: 命令执行结果包含预期字段
- **WHEN** 用户输入 `/system-info`
- **THEN** 输出中包含 project root 目录名或当前工作目录路径
```

