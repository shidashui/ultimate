# ---------------------------------------------------------------------------
# ANSI 颜色
# ---------------------------------------------------------------------------
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

def colored_prompt() -> str:
    return f"{CYAN}{BOLD}You > {RESET}"

def API_error_prompt(exc: Exception) -> str:
    return f"{YELLOW}API Error: {exc}{RESET}"

def print_assistant(text: str = "", end: str = '\n', flush: bool = False) -> None:
    print(f"\n{GREEN}{BOLD}Assistant:{RESET} {text}", end=end, flush=flush)

def print_tool(name: str, detail: str) -> None:
    """打印工具调用信息."""
    print(f"  {DIM}[tool: {name}] {detail}{RESET}")

def print_info(text: str) -> None:
    print(f"{DIM}{text}{RESET}")

def print_warn(text: str) -> None:
    print(f"{YELLOW}{text}{RESET}")

def print_session(text: str) -> None:
    print(f"{MAGENTA}{text}{RESET}")

def print_section(title: str) -> None:
    print(f"\n{MAGENTA}{BOLD}--- {title} ---{RESET}")

def print_context(pct: float, bar: str) -> None:
    color = get_color(pct)
    print(f"  {color}[{bar}] {pct:.1f}%{RESET}")

def print_tool_info(s: dict) -> None:
    print(f"  {BLUE}{s['invocation']}{RESET}  {s['name']} - {s['description']}")
    print(f"    {DIM}path: {s['path']}{RESET}")

def print_yellow_info(text: str) -> None:
    print(f"{YELLOW}{text}{RESET}")

def print_blue_info(text: str) -> None:
    print(f"{BLUE}{text}{RESET}")

def print_memory_info(r: dict) -> None:
    color = GREEN if r["score"] > 0.3 else DIM
    print(f"  {color}[{r['score']:.4f}]{RESET} {r['path']}")
    print(f"    {r['snippet']}")

def get_color(pct: float) -> str:
    if pct < 50:
        return GREEN
    elif pct < 80:
        return YELLOW
    else:
        return RED