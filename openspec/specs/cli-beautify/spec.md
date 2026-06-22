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
- `/prompt` 输出启用 Python 语法高亮
- 颜色主题支持用户自定义
