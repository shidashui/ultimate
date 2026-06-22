---
change: create-test-skills
design-doc: docs/superpowers/specs/2026-06-22-create-test-skills-design.md
base-ref: 3abd9965e72ed26407ce3d15d2bf28c73b9a39d5
archived-with: 2026-06-22-create-test-skills
---

# Test Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 3 个轻量级测试 skill（hello-skill, echo-args, system-info）用于验证项目的 skill 调用机制。

**Architecture:** 每个 skill 一个 `workspace/skills/<name>/SKILL.md`，包含 frontmatter 元数据和行为指令。SkillsManager 自动扫描发现。

**Tech Stack:** 仅 SKILL.md（Markdown + YAML frontmatter）

## Global Constraints

- SKILL.md 必须包含 `---` frontmatter，字段：name, description
- tasks.md 完成后勾选对应任务

archived-with: 2026-06-22-create-test-skills
---

### Task 1: hello-skill

**Files:**
- Create: `workspace/skills/hello-skill/SKILL.md`

- [ ] **Step 1: 创建 `workspace/skills/hello-skill/SKILL.md`**

```markdown
archived-with: 2026-06-22-create-test-skills
---
name: hello-skill
description: 最简单的测试 skill - 输出问候语
archived-with: 2026-06-22-create-test-skills
---

# Hello Skill

## 指令

当用户调用此 skill 时，输出一句问候语，包含 "Hello" 字样，并告知用户是通过 skill 调用的。
```

- [ ] **Step 2: 验证 `hello-skill` 可被识别**

```bash
ls workspace/skills/hello-skill/SKILL.md
```

Expected: 文件存在且非空

- [ ] **Step 3: 提交**

```bash
git add workspace/skills/hello-skill/SKILL.md
git commit -m "feat: add hello-skill test skill"
```

archived-with: 2026-06-22-create-test-skills
---

### Task 2: echo-args

**Files:**
- Create: `workspace/skills/echo-args/SKILL.md`

- [ ] **Step 1: 创建 `workspace/skills/echo-args/SKILL.md`**

```markdown
archived-with: 2026-06-22-create-test-skills
---
name: echo-args
description: 测试 skill - 接收参数并回显
archived-with: 2026-06-22-create-test-skills
---

# Echo Args Skill

## 指令

当用户调用此 skill 时：
1. 检查是否有传入参数（args）
2. 如果有参数，原样回显参数内容
3. 如果没有参数，输出 "No args provided"
```

- [ ] **Step 2: 验证文件创建**

```bash
ls workspace/skills/echo-args/SKILL.md
```

- [ ] **Step 3: 提交**

```bash
git add workspace/skills/echo-args/SKILL.md
git commit -m "feat: add echo-args test skill"
```

archived-with: 2026-06-22-create-test-skills
---

### Task 3: system-info

**Files:**
- Create: `workspace/skills/system-info/SKILL.md`

- [ ] **Step 1: 创建 `workspace/skills/system-info/SKILL.md`**

```markdown
archived-with: 2026-06-22-create-test-skills
---
name: system-info
description: 测试 skill - 输出当前系统环境信息
archived-with: 2026-06-22-create-test-skills
---

# System Info Skill

## 指令

当用户调用此 skill 时，执行以下 Bash 命令输出当前系统环境信息：

运行 `pwd` 和 `date` 命令，将结果展示给用户。
```

- [ ] **Step 2: 验证文件创建**

```bash
ls workspace/skills/system-info/SKILL.md
```

- [ ] **Step 3: 提交**

```bash
git add workspace/skills/system-info/SKILL.md
git commit -m "feat: add system-info test skill"
```
