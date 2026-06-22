---
comet_change: create-test-skills
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-22-create-test-skills
status: final
---

# Test Skills — 技术设计

## 背景

项目已有完善的 SkillsManager 机制（`agentd/skill/skill.py`），自动扫描多个路径发现 skill。新增测试 skill 用于验证：
1. Skill 工具可通过名称调用
2. 参数传递机制
3. Skill 内可执行命令

## 架构

```
workspace/skills/                     ← SkillsManager 自动扫描
├── hello-skill/SKILL.md              # 最简 skill，验证基本调用
├── echo-args/SKILL.md                # 参数回显，验证 args 传递
└── system-info/SKILL.md              # 命令执行，验证 shell 能力
```

## 各 Skill 规格

### hello-skill
- **描述**: 最简单的测试 skill
- **调用**: `/hello-skill` 或 Skill 工具 `skill="hello-skill"`
- **行为**: 输出问候语（含 "Hello" 字样）并告知调用方式
- **测试**: 直接 `/hello-skill` 应有回复

### echo-args
- **描述**: 接收参数并回显
- **调用**: `/echo-args <任意参数>`
- **行为**: 
  - 有参数时回显参数内容
  - 无参数时输出 "No args provided"
- **测试**: `/echo-args 测试` 应输出包含 "测试" 的内容

### system-info
- **描述**: 输出当前系统环境信息
- **调用**: `/system-info`
- **行为**: 执行 Bash 命令输出环境信息（目录、时间等）
- **测试**: `/system-info` 应包含项目根目录或工作路径

## 实现要点

- 每个 skill 仅需一个 `SKILL.md`，无额外文件依赖
- `SKILL.md` 需要 frontmatter（`name`、`description`）
- `invocation` 字段定义调用方式
- `body` 包含实现指令
