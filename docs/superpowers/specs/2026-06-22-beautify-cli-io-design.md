---
comet_change: beautify-cli-io
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-22-beautify-cli-io
status: final
---

# CLI 输入输出美化 — 技术设计

## 问题

当前 CLI 输出层基于手写 ANSI 转义码（`utils/print_tools.py`），AI 回复为纯文本，命令输出缺乏视觉层次。`rich` 15.0.0 已安装在环境中但未使用。

## 方案

用 `rich` 替换手写 ANSI 渲染：AI 回复通过 `rich.Markdown` 渲染，命令输出使用 `Panel`/`Table`/`Rule` 等结构化组件，统一色彩主题。

### 架构

```
cli/cli.py                    ← rich Table/Panel/Markdown 渲染命令+AI回复
utils/print_tools.py          ← rich Console + Theme 替换 ANSI 码
agentd/                       ← 不动（runner 返回纯文本，函数签名不变）
```

### Theme 设计

```python
THEME = Theme({
    "primary": "cyan bold",      # 用户提示符
    "success": "green bold",     # AI 回复标签
    "warning": "yellow",         # 警告
    "error": "red",              # 错误
    "muted": "dim",              # 辅助信息
    "accent": "magenta bold",    # 会话/分段标题
    "info": "blue",              # 信息高亮
})
```

### 函数迁移表

| 旧函数 | 新实现 | 签名变化 |
|--------|--------|----------|
| `colored_prompt()` | 返回纯字符串（prompt_toolkit 兼容） | 无 |
| `print_assistant()` | `console.print(text, style="success")` | 无 |
| `print_info()` | `console.print(text, style="muted")` | 无 |
| `print_warn()` | `console.print(text, style="warning")` | 无 |
| `print_session()` | `console.print(text, style="accent")` | 无 |
| `print_section()` | `console.print(Rule(title, style="accent"))` | 无 |
| `print_context()` | 保留颜色条 | 无 |
| `print_tool_info()` | `console.print(Columns(...))` | 无 |
| `print_yellow_info()` | `console.print(text, style="warning")` | 无 |
| `print_blue_info()` | `console.print(text, style="info")` | 无 |
| `print_memory_info()` | 结构化输出 | 无 |
| `get_color()` | inline 处理 | 保留 |

### 命令输出升级

| 命令 | 当前 | 升级后 |
|------|------|--------|
| 启动横幅 | `print_info` 逐行 | `Panel` 包裹 + `Rule` |
| `/help` | `print_info` 逐行 | `Table("命令", "说明")` |
| `/list` | `print_info` 逐行 | `Table` 5 列 |
| `/skills` | 逐条 | `Table` 3 列 |
| `/context` | 自绘进度条 | 保留颜色条 |
| `/memory` | 裸 print | `Panel` 包裹 |
| `/bootstrap` | 内联 ANSI | `Table` 2 列 |
| `/prompt` | 裸 print | `Panel` + 截断 |
| `/soul` | print_section | `Panel` |
| AI 回复 | `print_assistant(reply)` | `console.print(Markdown(reply))` |

### 边界条件

| 场景 | 处理 |
|------|------|
| AI 返回空文本 | `if reply:` 已有保护 |
| AI 返回含 ANSI 转义码 | `Markdown` 原样输出，不崩溃 |
| 超长 `/prompt` | 保留截断逻辑 |
| Windows cmd.exe | rich 自动降级纯文本 |
| 管道/重定向 | `is_terminal` 检测，自动去格式 |

### 关键取舍

- **一步到位**：直接改 `print_tools.py`，不建新文件，不留冗余
- **Markdown 总是渲染**：纯文本行为同 print，无需检测
- **ANSI 常量直接删除**：唯一引用者 `cli.py` 同步切换
- **agentd/ 函数签名不变**：4 个文件零修改

### 测试策略

- 手动验证：13 个命令 + AI 对话含代码块/表格/列表
- 回归：`python -c "from cli.cli import Cli; print('Build OK')"`
- 无需单元测试：渲染逻辑是 rich 内置能力
