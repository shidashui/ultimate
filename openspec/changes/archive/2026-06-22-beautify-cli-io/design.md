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
