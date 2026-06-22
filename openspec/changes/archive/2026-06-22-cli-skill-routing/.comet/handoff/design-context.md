# Comet Design Handoff

- Change: cli-skill-routing
- Phase: design
- Mode: compact
- Context hash: a51d3aeed7d6d203cbf0f19eb243d0e19c4e20774cbaf2e12d3c72627b4c770e

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/cli-skill-routing/proposal.md

- Source: openspec/changes/cli-skill-routing/proposal.md
- Lines: 1-31
- SHA256: 9c7436e12a83334f5bca62277c8cf91817a5a822060ce656f366a20f5fedc6f7

```md
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
```

## openspec/changes/cli-skill-routing/design.md

- Source: openspec/changes/cli-skill-routing/design.md
- Lines: 1-47
- SHA256: aa25a9fbc3cc8e632b2b648a81b8d82e88e016730ea8ef5c3a02c23b7d98ca18

```md
# Design: CLI Skill Routing

## 架构决策

```
用户输入 /comet 美化cli
        │
        ▼
handle_repl_command()
        │
        ├─ 1. 先匹配硬编码命令 (/help, /list, ...) → 原有逻辑
        │
        └─ 2. 未匹配 → 动态匹配 skills_mgr.skills
              │
              ├─ 命中 "comet" (invocation="/comet")
              │   ├─ console.print("[技能] comet 触发")
              │   ├─ 将 skill body 注入 messages 作为系统上下文
              │   ├─ 调用 AI runner.run_turn(user_input, messages, ...)
              │   └─ return True
              │
              └─ 未命中 → return False → 普通 AI 对话
```

## 关键设计选择

### 1. 动态补全
- `WordCompleter` 改为从 `skills_mgr.skills` 读取 `invocation` 字段
- 硬编码命令列表和技能列表合并为一个 `get_completions()` 方法
- 每次 `discover()` 后自动刷新补全列表

### 2. 技能路由
- 在 `handle_repl_command` 末尾（硬编码命令之后）增加动态技能匹配
- 匹配方式：`cmd` 去掉前缀 `/` 后与 skill 的 `name` 字段比较，或用 `invocation` 字段比较
- 命中后：显示触发反馈 + 将 skill body 注入为 system message + 调用 AI

### 3. 上下文注入
- Skill body 作为 `{"role": "system", "content": skill_body}` 临时插入消息列表
- 用户原始输入（含 `/comet` 前缀）保留为 user message
- 注入的 system message 不持久化到 session

### 4. /help 集成
- 在 `/help` 输出末尾追加"可用技能"段，从 `skills_mgr.skills` 动态生成

## 技术风险

- **Skill body 过长**：截断到 MAX_TOTAL_CHARS 限制内，超长时只注入前 N 字符 + 提示
- **循环依赖**：`skills_mgr` 在 `init_run()` 之后才可用，补全列表需延迟初始化
```

## openspec/changes/cli-skill-routing/tasks.md

- Source: openspec/changes/cli-skill-routing/tasks.md
- Lines: 1-15
- SHA256: 49c07b71bc23ce36520dc6d86efe902d8d46a00b105424c01df4d1119ea525a4

```md
# Tasks: CLI Skill Routing

- [ ] **Task 1: 动态 Tab 补全**
  - `WordCompleter` 从 `skills_mgr.skills` 的 `invocation` 字段读取技能名
  - 保持硬编码命令和动态技能名合并
  - 无需刷新机制（启动时已有）

- [ ] **Task 2: 技能路由**
  - 在 `handle_repl_command` 末尾增加动态技能匹配
  - 命中后显示触发反馈（console.print）
  - Skill body 作为 system message 注入后调用 AI

- [ ] **Task 3: /help 集成**
  - `/help` 输出末尾追加"可用技能"段
  - 从 `skills_mgr.skills` 动态生成行
```

