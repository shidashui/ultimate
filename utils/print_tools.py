# utils/print_tools.py
from rich.console import Console
from rich.theme import Theme
from rich.rule import Rule
from rich.columns import Columns
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

from prompt_toolkit.formatted_text import FormattedText

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
def colored_prompt():
    """返回 prompt_toolkit FormattedText（原生样式，不经过 rich→ANSI）。"""
    return FormattedText([("ansicyan bold", "You > ")])


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
