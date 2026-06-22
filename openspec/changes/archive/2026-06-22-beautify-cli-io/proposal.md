# Proposal: 美化 CLI 输入输出

## 问题

当前 CLI 输出层基于手写 ANSI 转义码（`utils/print_tools.py`），存在以下问题：

1. **AI 回复为纯文本**：Agent 返回的 Markdown 格式消息（代码块、表格、列表、加粗、斜体）全部以原始字符显示，可读性差
2. **命令输出无层次**：`/help`、`/list`、`/skills` 等命令的输出是简单的缩进文本，缺少视觉分组
3. **色彩体系不一致**：`print_tools.py` 中颜色零散定义，缺少统一主题
4. **rich 库已安装但未使用**：`rich` 15.0.0 提供了 Markdown 渲染、Panel、Table、语法高亮、进度条等能力，完全未利用

## 目标

用 `rich` 替换手写 ANSI 渲染，全面提升 CLI 视觉体验：

- AI 回复通过 `rich.Markdown` 渲染，代码块自动语法高亮
- 命令输出使用 Panel、Table、Rule 等结构化组件
- 统一色彩主题，输出不再依赖原始 ANSI 转义码

## 范围

- **改**：`utils/print_tools.py` — 底层迁移到 rich Console + 统一主题
- **改**：`cli/cli.py` — 命令输出改用 rich 组件，AI 回复经 Markdown 渲染
- **不动**：`agentd/` 核心逻辑、输入层（prompt_toolkit 已足够）

## 非目标

- 不改变 REPL 循环控制流
- 不添加新的命令
- 不改变 Gateway/API 端的输出（仅 CLI）
