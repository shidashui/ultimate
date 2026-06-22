# Comet Design Handoff

- Change: cli-tab-completion
- Phase: design
- Mode: compact
- Context hash: 46df3051cc20f109db0f20148252c6144e9b8cac0f8053086cfcbabe75cd6c16

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/cli-tab-completion/proposal.md

- Source: openspec/changes/cli-tab-completion/proposal.md
- Lines: 1-24
- SHA256: 0c09f695acfba4ebb9a04cba0d29fd17476298a8aa3e0e8037eee3fde3c07c86

```md
## Why

当前 CLI 交互使用 Python 内置 `input()` 函数，无任何命令补全能力。用户需要完整记住 `/switch`、`/compact`、`/bootstrap` 等命令名称和参数格式，使用体验差、学习成本高。每次手打完整命令也容易拼写错误。

## What Changes

- 安装 `prompt_toolkit` 依赖
- 替换 `cli/cli.py` 中的 `input()` 为 `prompt_toolkit.PromptSession`
- 实现 Tab 补全逻辑：`/` 开头时补全 REPL 命令，普通输入无补全

## Capabilities

### New Capabilities
- `tab-completion`: REPL 命令 Tab 补全能力

### Modified Capabilities
- （无）

## Impact

- **依赖新增**: `prompt_toolkit`（单文件纯 Python，无 native 扩展，安装轻量）
- **修改文件**: `cli/cli.py` — 替换输入循环，增加 completer
- **新增文件**: 无
- **无行为破坏**: 所有现有命令、会话机制、配色、输出格式完全不变
```

## openspec/changes/cli-tab-completion/design.md

- Source: openspec/changes/cli-tab-completion/design.md
- Lines: 1-43
- SHA256: 9e9f32d1a66c6ebd62b0ab1e1817df8da4decfa1de217984b902e9e87e902921

```md
## 技术方案

### 架构

```
输入循环

▼
PromptSession(shell_completer)
    │
    ├── 输入 "/" → WordCompleter 补全命令
    │                    └── REPL_COMMANDS.keys() → 命令名
    │                    └── 命令名 + " <arg>" → 带参数提示
    │
    └── 其他 → 无补全（原有行为）
```

### 方案选择

| 方案 | 说明 | 评估 |
|------|------|------|
| A. prompt_toolkit | 标准交互补全库，Tab 补全 + 历史记录 + 多行编辑 | **选此方案** |
| B. msvcrt 手写 | Windows 原生 getch 逐字符处理 | 基础功能，无历史记录，兼容性差 |
| C. rich 的 Prompt | rich 有 Prompt.ask 但无补全 | 不够用 |

### Prompt_toolkit 补全实现

- `WordCompleter`: 对 `/` 前缀的命令做模糊匹配
- 补全词表: 从 `handle_repl_command` 中现有的所有命令硬编码 + 动态读取 `skills_mgr.skills` 中的 skill 名
- 命令后自动加空格，方便继续输入参数

### 文件变更

- `cli/cli.py`:
  - 导入: `from prompt_toolkit import PromptSession`
  - 导入: `from prompt_toolkit.completion import WordCompleter`
  - 替换 `input(colored_prompt())` 为 `session.prompt(colored_prompt())`
  - 在 `__init__` 中构造 `PromptSession` + `WordCompleter`

### 风险

- `prompt_toolkit` 在 Windows 上依赖 `colorama`（已装）和 `pyreadline`（会作为依赖自动安装），无额外风险
- `prompt_toolkit` 的 `PromptSession` 自带历史记录，不会破坏现有 SessionStore
```

## openspec/changes/cli-tab-completion/tasks.md

- Source: openspec/changes/cli-tab-completion/tasks.md
- Lines: 1-4
- SHA256: 6a7c066a06f0c2eb3126d48b0ca7a9870bd99f2fb92a5802da99f43cfeb5bf8a

```md
# Tasks: cli-tab-completion

- [ ] Task 1: 安装依赖 `pip install prompt_toolkit`
- [ ] Task 2: 在 `cli/cli.py` 中替换 `input()` 为 `PromptSession`，添加 Tab 补全
```

## openspec/changes/cli-tab-completion/specs/tab-completion/spec.md

- Source: openspec/changes/cli-tab-completion/specs/tab-completion/spec.md
- Lines: 1-45
- SHA256: 377a4abd438ff3246fadf3a72994851517f8e9ce760133d0c22bfbe513f6c0ce

```md
# Tab Completion Spec

## ADDED Requirements

### Requirement: Tab 补全 REPL 命令

用户在 REPL 中输入以 `/` 开头的命令时，按 Tab 键应弹出补全候选列表。

- **补全词表**: `/new`, `/list`, `/switch`, `/context`, `/compact`, `/soul`, `/skills`, `/memory`, `/search`, `/prompt`, `/bootstrap`, `/help`, `/quit`, `/exit`
- **触发条件**: 输入以 `/` 开头时自动激活补全
- **历史记录**: 无需额外配置，PromptSession 自带

#### Scenario: 输入 / 后按 Tab 显示全部命令

```
You > /<Tab>
/new       /list      /switch    /context   /compact
/soul      /skills    /memory    /search    /prompt
/bootstrap /help      /quit      /exit
```

#### Scenario: 输入 /s 后按 Tab 补全

```
You > /s<Tab>
→ 补全为 /search（或者显示 /soul /search /skills 候选列表）
```

#### Scenario: 补全后继续输入参数

```
You > /switch <Tab> 无需补全，保持当前输入
```

### Future: Tab 补全技能名称（当前版本暂不做）

当前 command 数少，skill 补全价值低。等 skill 数量增长后再加。

- **补全来源**: `SkillsManager.skills` 动态获取
- **实现方式**: 在 `REPL_COMMANDS` 基础上拼接 `[f"/{s['name']}" for s in skills_mgr.skills]`
- **触发条件**: 输入 `/` 后匹配到未注册命令时，尝试匹配 skill 名

### Requirement: 不影响非补全输入

用户输入不以 `/` 开头的普通文本时，Tab 无任何补全行为，按 Tab 跳出 4 空格或保持原有行为。
```

