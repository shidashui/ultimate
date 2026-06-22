---
change: beautify-cli-io
design-doc: docs/superpowers/specs/2026-06-22-beautify-cli-io-design.md
base-ref: 7ba3915f0c070f42fd8e3ae03d63e4dde988bfe3
archived-with: 2026-06-22-beautify-cli-io
---

# CLI 输出美化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 `rich` 替换 `print_tools.py` 中手写 ANSI 码，`cli.py` 中 AI 回复用 Markdown 渲染、命令输出用 Table/Panel 结构化。

**Architecture:** 一步到位：重写 `print_tools.py` 内部为 rich Console + Theme（函数签名不变），`cli.py` 直接使用 rich 组件渲染命令输出和 AI 回复。

**Tech Stack:** Python, rich 15.0.0, prompt_toolkit 3.0.52

## Global Constraints

- print_tools.py 所有函数签名保持不变（agentd/ 4 个文件零修改）
- ANSI 常量从 print_tools.py 移除（唯一引用者 cli.py 同步切换）
- build_command: `python -c "from cli.cli import Cli; print('Build OK')"`
- 改动范围限于 print_tools.py + cli/cli.py + tasks.md

archived-with: 2026-06-22-beautify-cli-io
---

### Task 1: 重构 print_tools.py — 迁移到 rich

**Files:**
- Modify: `utils/print_tools.py` — 全部重写

**Interfaces:**
- Consumes: 无
- Produces: `console` (rich Console 实例), `colored_prompt()`, `print_assistant()`, `print_tool()`, `print_info()`, `print_warn()`, `print_session()`, `print_section()`, `print_context()`, `print_tool_info()`, `print_yellow_info()`, `print_blue_info()`, `print_memory_info()`, `get_color()`, `API_error_prompt()`

- [ ] **Step 1: 替换 print_tools.py 全部内容**

将 `utils/print_tools.py` 完整替换为以下内容：

```python
# utils/print_tools.py
from rich.console import Console
from rich.theme import Theme
from rich.rule import Rule
from rich.columns import Columns
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

# ── Rich Console + 统一 Theme ──────────────────────────────
THEME = Theme({
    "primary": "cyan bold",      # 用户提示符
    "success": "green bold",     # AI 回复 / 通过
    "warning": "yellow",         # 警告
    "error":   "red",            # 错误
    "muted":   "dim",            # 辅助信息
    "accent":  "magenta bold",   # 会话 / 分段标题
    "info":    "blue",           # 信息高亮
})

console = Console(theme=THEME)


# ── 提示符函数 ────────────────────────────────────────────
def colored_prompt() -> str:
    """返回 prompt_toolkit 可用的用户提示符字符串。"""
    return "[primary]You > [/primary]"


def API_error_prompt(exc: Exception) -> str:
    return f"[warning]API Error: {exc}[/warning]"


# ── 输出函数（签名不变）────────────────────────────────────
def print_assistant(text: str = "", end: str = '\n', flush: bool = False) -> None:
    """打印 Assistant 标签（不含内容渲染，内容由调用方用 Markdown 渲染）。"""
    console.print(f"\n[success]Assistant:[/success] {text}", end=end)


def print_tool(name: str, detail: str) -> None:
    """打印工具调用信息。"""
    console.print(f"  [muted][tool: {name}] {detail}[/muted]")


def print_info(text: str) -> None:
    console.print(f"[muted]{text}[/muted]")


def print_warn(text: str) -> None:
    console.print(f"[warning]{text}[/warning]")


def print_session(text: str) -> None:
    console.print(f"[accent]{text}[/accent]")


def print_section(title: str) -> None:
    console.print()
    console.print(Rule(title=title, style="accent"))


def print_context(pct: float, bar: str) -> None:
    """保留颜色进度条逻辑。"""
    color = get_color(pct)
    console.print(f"  [{color}][{bar}] {pct:.1f}%[/{color}]")


def print_tool_info(s: dict) -> None:
    """技能信息结构化输出。"""
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column("invoke", style="info", no_wrap=True)
    table.add_column("detail")
    table.add_row(s['invocation'], f"{s['name']} - {s['description']}")
    table.add_row("", f"[muted]path: {s['path']}[/muted]")
    console.print(table)


def print_yellow_info(text: str) -> None:
    console.print(f"[warning]{text}[/warning]")


def print_blue_info(text: str) -> None:
    console.print(f"[info]{text}[/info]")


def print_memory_info(r: dict) -> None:
    """记忆搜索结果输出。"""
    color = "success" if r["score"] > 0.3 else "muted"
    console.print(f"  [{color}][{r['score']:.4f}][/{color}] {r['path']}")
    console.print(f"    {r['snippet']}")


def get_color(pct: float) -> str:
    """返回 rich style 名称（替代旧 ANSI 颜色）。"""
    if pct < 50:
        return "success"
    elif pct < 80:
        return "warning"
    else:
        return "error"
```

- [ ] **Step 2: 验证 print_tools.py 可导入**

```bash
python -c "from utils.print_tools import *; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 验证现有 agentd/ 调用不报错**

```bash
python -c "from agentd.tools.skill_tools import *; from agentd.tools.registry import *; from agentd.context.context import ContextGuard; from agentd.tools.memory_tools import *; from agentd.tools.file_tools import *; print('All imports OK')"
```

Expected: `All imports OK`

- [ ] **Step 4: Commit**

```bash
git add utils/print_tools.py
git commit -m "refactor: migrate print_tools.py from raw ANSI to rich Console + Theme

Replace manual ANSI escape codes with rich Theme-based styling.
All function signatures preserved — agentd/ consumers unchanged.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-22-beautify-cli-io
---

### Task 2: AI 回复 Markdown 渲染

**Files:**
- Modify: `cli/cli.py:1-12` — 添加 rich.Markdown 导入
- Modify: `cli/cli.py:88` — `print_assistant(reply)` → `console.print(Markdown(reply))`

**Interfaces:**
- Consumes: `console` from print_tools, `Markdown` from rich
- Produces: 渲染后的 AI 回复输出

- [ ] **Step 1: 在 cli.py 顶部添加 Markdown 导入**

原代码第 3 行：
```python
from utils.print_tools import *
```

在其后添加：
```python
from rich.markdown import Markdown
```

- [ ] **Step 2: 替换 AI 回复输出**

原代码 `handle_user_input` 方法第 87-88 行：
```python
        if reply:
            print_assistant(reply)
```

改为：
```python
        if reply:
            console.print()
            console.print("Assistant:", style="success", end=" ")
            console.print(Markdown(reply))
```

- [ ] **Step 3: Build 验证**

```bash
python -c "from cli.cli import Cli; print('Build OK')"
```

Expected: `Build OK`

- [ ] **Step 4: Commit**

```bash
git add cli/cli.py
git commit -m "feat: render AI replies with rich.Markdown for syntax highlighting

AI responses now go through rich.Markdown() — code blocks get syntax
highlighting, tables and lists render natively in terminal.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-22-beautify-cli-io
---

### Task 3: 命令输出结构化升级

**Files:**
- Modify: `cli/cli.py:27-53` — `init_run()` 启动横幅
- Modify: `cli/cli.py:102-239` — 所有 `/` 命令输出

**Interfaces:**
- Consumes: `console`, `Panel`, `Table`, `Rule` from print_tools/rich
- Produces: 结构化命令输出

- [ ] **Step 1: 升级 init_run() 启动横幅**

原代码第 42-53 行：
```python
        print_info("=" * 60)
        print_info("  ultimate agent 启动成功！ ")
        print_info(f"  当前模型: {MODEL['name']}")
        print_info(f"  会话ID: {self.store.current_session_id}")
        print_info(f"  当前工具列表: {', '.join(self.runner.container.tools_handlers.keys())}")
        print_info(f"  工作区: {WORKSPACE_DIR}")
        print_info(f"  已加载文件: {len(self.runner.bootstrap_data)}")
        print_info(f"  已发现技能: {len(self.runner.skills_mgr.skills)}")
        stats = self.runner.memory_store.get_stats()
        print_info(f"  记忆: 长期 {stats['evergreen_chars']}字符, {stats['daily_files']} 个每日文件")
        print_info("  输入/help获取指令帮助, 输入/quit或者/exit退出。")
        print_info("=" * 60)
```

改为：
```python
        stats = self.runner.memory_store.get_stats()
        info_lines = [
            f"[primary]当前模型:[/primary] {MODEL['name']}",
            f"[primary]会话ID:[/primary] {self.store.current_session_id}",
            f"[primary]工具列表:[/primary] {', '.join(self.runner.container.tools_handlers.keys())}",
            f"[primary]工作区:[/primary] {WORKSPACE_DIR}",
            f"[primary]已加载文件:[/primary] {len(self.runner.bootstrap_data)}",
            f"[primary]已发现技能:[/primary] {len(self.runner.skills_mgr.skills)}",
            f"[primary]记忆:[/primary] 长期 {stats['evergreen_chars']}字符, {stats['daily_files']} 个每日文件",
        ]
        console.print()
        console.print(Panel(
            "\n".join(info_lines),
            title="ultimate agent 启动成功！",
            title_align="center",
            border_style="primary",
        ))
        console.print("[muted]  /help 获取指令帮助, /quit 或 /exit 退出[/muted]")
```

- [ ] **Step 2: 升级 /help 命令**

原代码第 222-237 行的 `/help` 分支改为：
```python
        elif cmd == "/help":
            console.print()
            help_table = Table(title="REPL 命令", border_style="muted")
            help_table.add_column("命令", style="info", no_wrap=True)
            help_table.add_column("说明")
            for cmd_name, desc in [
                ("/new [label]", "创建新会话"),
                ("/list", "列出所有会话"),
                ("/switch <id>", "切换到指定会话（前缀匹配）"),
                ("/context", "显示上下文 token 用量"),
                ("/compact", "手动压缩对话历史"),
                ("/soul", "显示 SOUL.md 内容"),
                ("/skills", "列出已发现的技能"),
                ("/memory", "显示记忆统计"),
                ("/search <query>", "搜索记忆"),
                ("/prompt", "显示完整系统提示词"),
                ("/bootstrap", "显示已加载的 Bootstrap 文件"),
                ("/help", "显示此帮助"),
                ("/quit /exit", "退出 REPL"),
            ]:
                help_table.add_row(cmd_name, desc)
            console.print(help_table)
            return True
```

- [ ] **Step 3: 升级 /list 命令**

原代码第 108-120 行的 `/list` 分支改为：
```python
        elif cmd == "/list":
            sessions = self.store.list_sessions()
            if not sessions:
                console.print("[muted]  No sessions found.[/muted]")
                return True
            list_table = Table(title="会话列表", border_style="muted")
            list_table.add_column("ID", style="info", no_wrap=True)
            list_table.add_column("标签")
            list_table.add_column("消息数")
            list_table.add_column("最后活跃")
            list_table.add_column("", no_wrap=True)
            for sid, meta in sessions:
                active = "<--" if sid == self.store.current_session_id else ""
                label = meta.get("label", "")
                count = str(meta.get("message_count", 0))
                last = meta.get("last_active", "?")[:19]
                list_table.add_row(sid, label, count, last, active)
            console.print(list_table)
            return True
```

- [ ] **Step 4: 升级 /skills 命令**

原代码第 166-173 行的 `/skills` 分支改为：
```python
        elif cmd == "/skills":
            console.print(Rule(title="已发现的技能", style="accent"))
            if not self.runner.skills_mgr.skills:
                console.print("[muted](未发现技能)[/muted]")
            else:
                sk_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
                sk_table.add_column("invoke", style="info", no_wrap=True)
                sk_table.add_column("detail")
                for s in self.runner.skills_mgr.skills:
                    sk_table.add_row(s['invocation'], f"{s['name']} - {s['description']}")
                    sk_table.add_row("", f"[muted]path: {s['path']}[/muted]")
                console.print(sk_table)
            return True
```

- [ ] **Step 5: 升级 /context 命令（无变化，保留现有逻辑）**

现有的 `/context` 颜色条（第 139-148 行）保持不变：
```python
        elif cmd == "/context":
            estimated = self.runner.guard.estimate_messages_tokens(self.messages)
            pct = (estimated / self.runner.guard.max_tokens) * 100
            bar_len = 30
            filled = int(bar_len * min(pct, 100) / 100)
            bar = "#" * filled + "-" * (bar_len - filled)
            console.print(f"  [muted]Context usage: ~{estimated:,} / {self.runner.guard.max_tokens:,} tokens[/muted]")
            print_context(pct, bar)
            console.print(f"  [muted]Messages: {len(self.messages)}[/muted]")
            return True
```

- [ ] **Step 6: 升级 /memory 命令**

原代码第 175-181 行的 `/memory` 分支改为：
```python
        elif cmd == "/memory":
            stats = self.runner.memory_store.get_stats()
            mem_text = (
                f"  长期记忆 (MEMORY.md): {stats['evergreen_chars']} 字符\n"
                f"  每日文件: {stats['daily_files']}\n"
                f"  每日条目: {stats['daily_entries']}"
            )
            console.print(Panel(mem_text, title="记忆统计", border_style="accent"))
            return True
```

- [ ] **Step 7: 升级 /bootstrap 命令**

原代码第 211-220 行的 `/bootstrap` 分支改为：
```python
        elif cmd == "/bootstrap":
            console.print(Rule(title="Bootstrap 文件", style="accent"))
            if not self.runner.bootstrap_data:
                console.print("[muted](未加载 Bootstrap 文件)[/muted]")
            else:
                bsk_table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
                bsk_table.add_column("name", style="info")
                bsk_table.add_column("size")
                for name, content in self.runner.bootstrap_data.items():
                    bsk_table.add_row(name, f"{len(content)} chars")
                console.print(bsk_table)
            total = sum(len(v) for v in self.runner.bootstrap_data.values())
            console.print(f"  [muted]总计: {total} 字符 (上限: {MAX_TOTAL_CHARS})[/muted]")
            return True
```

- [ ] **Step 8: 升级 /prompt 命令**

原代码第 196-209 行的 `/prompt` 分支改为：
```python
        elif cmd == "/prompt":
            console.print(Rule(title="完整系统提示词", style="accent"))
            prompt = build_system_prompt(
                mode="full", bootstrap=self.runner.bootstrap_data,
                skill_registry=self.runner.skill_registry,
                channel="terminal",
            )
            if len(prompt) > 3000:
                console.print(Panel(prompt[:3000] + "\n", title="System Prompt (truncated)"))
                console.print(f"[muted]... ({len(prompt) - 3000} more chars, total {len(prompt)})[/muted]")
            else:
                console.print(Panel(prompt, title="System Prompt"))
            console.print(f"[muted]提示词总长度: {len(prompt)} 字符[/muted]")
            return True
```

- [ ] **Step 9: 升级 /soul 命令**

原代码第 160-164 行的 `/soul` 分支改为：
```python
        elif cmd == "/soul":
            console.print(Rule(title="SOUL.md", style="accent"))
            soul = self.runner.bootstrap_data.get("SOUL.md", "")
            if soul:
                console.print(soul)
            else:
                console.print("[muted](未找到 SOUL.md)[/muted]")
            return True
```

- [ ] **Step 10: Build 验证**

```bash
python -c "from cli.cli import Cli; print('Build OK')"
```

Expected: `Build OK`

- [ ] **Step 11: Commit**

```bash
git add cli/cli.py
git commit -m "feat: upgrade all REPL command outputs with rich Table/Panel/Rule

/help → Table, /list → Table, /skills → Table, /memory → Panel,
/bootstrap → Table, /prompt → Panel, /soul → Rule, init banner → Panel.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-22-beautify-cli-io
---

### Task 4: 清理与最终验证

**Files:**
- Modify: `utils/print_tools.py` — 确认无残留 ANSI 常量
- Modify: `openspec/changes/beautify-cli-io/tasks.md` — 全部勾选

**Interfaces:**
- Consumes: 完成的任务 1-3
- Produces: 干净提交 + 验证通过

- [ ] **Step 1: 确认无外部文件引用旧 ANSI 常量**

```bash
grep -rn "from utils.print_tools import \*" --include="*.py" . 2>/dev/null || echo "only cli.py"
```

Expected: 仅 `cli/cli.py`（已重写，不再使用 ANSI 常量）

- [ ] **Step 2: 运行构建命令**

```bash
python -c "from cli.cli import Cli; print('Build OK')"
```

Expected: `Build OK`

- [ ] **Step 3: 验证 agentd/ 全量导入**

```bash
python -c "from agentd.bootstrap.container import *; from agentd.agent.runner import AgentRunner; from agentd.tools.skill_tools import *; from agentd.tools.registry import *; from agentd.tools.memory_tools import *; from agentd.tools.file_tools import *; from agentd.context.context import ContextGuard; print('All imports OK')"
```

Expected: `All imports OK`

- [ ] **Step 4: 勾选 tasks.md 全部任务**

将 `openspec/changes/beautify-cli-io/tasks.md` 中所有 `- [ ]` 改为 `- [x]`

- [ ] **Step 5: Commit**

```bash
git add openspec/changes/beautify-cli-io/tasks.md
git commit -m "chore: mark all tasks complete for beautify-cli-io

Co-Authored-By: Claude <noreply@anthropic.com>"
```
