# Comet Design Handoff

- Change: beautify-cli-io
- Phase: design
- Mode: compact
- Context hash: 55a8ebeec1709e7fea23b9d6ffd1ea8d9c9a5c4823ebf199228144e7726f5367

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/beautify-cli-io/proposal.md

- Source: openspec/changes/beautify-cli-io/proposal.md
- Lines: 1-30
- SHA256: 80f4cc831da5dcb8742d09ec05c6bafb06fdcdab1d5bbcec5c8082b43d030fed

```md
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
```

## openspec/changes/beautify-cli-io/design.md

- Source: openspec/changes/beautify-cli-io/design.md
- Lines: 1-50
- SHA256: 93e3bb953d461c7d5d0b7a7dcf440293359982ccd8e70a3379eb356edb9ca480

```md
# Design: 美化 CLI 输入输出

## 架构决策

### 渲染引擎：rich

`rich` 已在环境中（15.0.0），提供：
- `Console` — 统一输出对象，自动处理 Windows 颜色
- `Markdown` — Markdown → 终端富文本，代码块自动语法高亮
- `Panel` / `Table` / `Rule` / `Columns` — 结构化布局
- `Theme` — 统一色彩管理

### 分层策略

```
┌────────────────────────────┐
│         cli/cli.py         │  ← 用 rich 组件重构命令输出
│    handle_repl_command()   │
├────────────────────────────┤
│    utils/print_tools.py    │  ← 迁移到 rich Console + Theme
│   (底层输出函数 + 色彩)     │
├────────────────────────────┤
│    agentd/agent/runner.py  │  ← 不动，继续返回纯文本
└────────────────────────────┘
```

- `runner.run_turn()` 返回纯文本（不变）
- `cli.py` 收到文本后，用 `rich.Markdown` 渲染再输出
- 命令输出用 rich 组件（Panel、Table）直接替换

### 兼容性

- `print_tools.py` 所有函数签名保持不变
- 内部改用 `console.print()` 替代 `print()`
- 色彩常量（CYAN、GREEN 等）保留但标记 deprecated，内部用 Theme 映射
- colorama 不再需要单独使用（rich 已处理 Windows）

## 技术风险

| 风险 | 缓解 |
|------|------|
| Markdown 渲染误解析非 Markdown 文本 | rich.Markdown 对纯文本行为等同 print，不会破坏现有输出 |
| 长文本 /help 输出性能 | rich 对大型 Table/Markdown 有内部缓存，无明显性能问题 |
| Windows Terminal 兼容性 | rich + colorama 已广泛验证，支持 Windows Terminal / cmd / PowerShell |

## 测试策略

- 手动测试每个 `/` 命令的输出渲染
- 发送包含代码块、表格、列表的提示词，验证 Markdown 渲染
- 确认 `print_tools.py` 旧函数向后兼容（现有调用方无需修改）
```

## openspec/changes/beautify-cli-io/tasks.md

- Source: openspec/changes/beautify-cli-io/tasks.md
- Lines: 1-48
- SHA256: bdcfe794762e4d893cfa70b59ebaf25c2a0e75ced708b2c8b71d02d374ac48ce

```md
# Tasks: 美化 CLI 输入输出

## 任务清单

### Task 1: 重构 print_tools.py — 迁移到 rich

- [ ] **Step 1: 创建 rich Console 实例与统一 Theme**
  - 定义 Theme 映射（primary=cyan, success=green, warning=yellow, error=red, muted=dim, accent=magenta, info=blue）
  - 创建全局 `console` 实例
  - 保留旧 ANSI 常量但标记 deprecated

- [ ] **Step 2: 重写所有输出函数**
  - `print_assistant()` → `console.print()` + Style
  - `print_info/warn/session/section()` → `console.print()` + 对应 Style
  - `print_tool_info()` → 使用 rich.Table 或 Columns
  - `print_context()` → 使用 rich 进度条
  - `print_memory_info()` → 结构化输出
  - `get_color()` → 用 Theme 色阶替代

- [ ] **Step 3: 向后兼容验证**
  - 确认所有现有调用方（cli.py 及其他）无需修改参数

### Task 2: 美化 AI 回复渲染

- [ ] **Step 1: 在 cli.py 导入 rich.Markdown**
- [ ] **Step 2: 修改 run() 中 AI 回复输出**
  - `print_assistant(reply)` → `console.print(Markdown(reply))`
- [ ] **Step 3: 处理边界情况**
  - 空回复不渲染
  - 纯文本回复正常显示（不破坏格式）

### Task 3: 美化命令输出

- [ ] **Step 1: `/help` — 用 rich.Table 排版命令列表**
- [ ] **Step 2: `/list` — 用 rich.Table 排版会话列表**
- [ ] **Step 3: `/skills` — 用 rich.Table 排版技能列表**
- [ ] **Step 4: `/context` — 用 rich 进度条组件**
- [ ] **Step 5: `/memory` — 用 Panel 包裹统计信息**
- [ ] **Step 6: `/bootstrap` — 用 rich.Table 排版文件列表**
- [ ] **Step 7: `/prompt` — 用 Panel + 语法高亮渲染系统提示词**
- [ ] **Step 8: `/soul` — 用 Panel 包裹 SOUL 内容**
- [ ] **Step 9: init_run() — 升级启动横幅为 rich Panel**

### Task 4: 清理与验证

- [ ] **Step 1: 删除 print_tools.py 中不再需要的 ANSI 常量**
- [ ] **Step 2: 全量手动验证** — 启动 `python ultimate.py chat`，逐一测试所有 13 个命令 + AI 对话
- [ ] **Step 3: Commit**
```

## openspec/changes/beautify-cli-io/specs/cli-beautify/spec.md

- Source: openspec/changes/beautify-cli-io/specs/cli-beautify/spec.md
- Lines: 1-82
- SHA256: 6481474c1ad88e19e77e3a068d5a8c58ef63559df3293d7e89ae2201d14d1ca3

[TRUNCATED]

```md
# CLI 输出美化 Spec

## Requirements

### Requirement: AI 回复 Markdown 渲染

Agent 返回的文本回复通过 `rich.Markdown` 渲染后输出到终端。

- 代码块自动语法高亮
- 表格、列表、加粗、斜体等 Markdown 元素正确渲染
- 纯文本回复渲染后与普通 print 表现一致（无格式破坏）

#### Scenario: 代码块渲染

```
You > 请写一个 Python hello world
Assistant: (渲染后的回复，代码块带语法高亮)
```

#### Scenario: 纯文本渲染

```
You > 你好
Assistant: 你好！有什么可以帮你的？ (颜色为 green bold，文本无额外格式)
```

### Requirement: 命令输出结构化

所有 `/` REPL 命令的输出使用 rich 结构化组件代替纯文本缩进。

- `/help` 使用 `Table` 双栏排版
- `/list` 使用 `Table` 多栏排版
- `/skills` 使用 `Table` 排版
- `/context` 保留颜色进度条
- `/memory` 使用 `Panel` 包裹
- `/bootstrap` 使用 `Table` 排版
- 启动横幅使用 `Panel` 包裹

#### Scenario: /help 命令

```
You > /help
┌────────────┬────────────────────────────┐
│ 命令       │ 说明                       │
├────────────┼────────────────────────────┤
│ /new       │ Create a new session       │
│ /list      │ List all sessions          │
│ ...        │ ...                        │
└────────────┴────────────────────────────┘
```

#### Scenario: /list 命令

```
You > /list
┌──────────┬─────────┬──────┬─────────────┬────────┐
│ ID       │ Label   │ Msgs │ Last Active │ Status │
├──────────┼─────────┼──────┼─────────────┼────────┤
│ abc123.. │ initial │ 12   │ ...         │ active │
└──────────┴─────────┴──────┴─────────────┴────────┘
```

### Requirement: 色彩体系统一

所有 CLI 输出通过 rich Theme 统一管理色彩，不再使用原始 ANSI 转义码。

- agentd/ 中 4 个文件对 `print_tools.py` 函数的调用无需修改
- ANSI 常量（CYAN, GREEN 等）从 `print_tools.py` 中移除

#### Scenario: 色彩向后兼容

```
# agentd/context/context.py 中的以下调用无需修改：
from utils.print_tools import print_session, print_warn
print_session("compacting...")  # 输出颜色与迁移前一致
```

## Future

- 流式输出（streaming）时逐 token 渲染 Markdown
```

Full source: openspec/changes/beautify-cli-io/specs/cli-beautify/spec.md

