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
