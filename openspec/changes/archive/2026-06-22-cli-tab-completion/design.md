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
