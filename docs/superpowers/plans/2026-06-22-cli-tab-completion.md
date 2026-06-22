# CLI Tab 补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 REPL 添加 Tab 命令补全，解决 `input()` 无补全问题。

**Architecture:** 用 `prompt_toolkit` 的 `PromptSession` + `WordCompleter` 替换裸 `input()`，补全 `/` 开头的 REPL 命令列表。

**Tech Stack:** Python, prompt_toolkit, colorama (已有)

## Global Constraints

- prompt_toolkit 版本不限，最新版即可
- 修改仅限于 `cli/cli.py`，不侵入 agentd/ 核心
- 所有现有命令处理逻辑不动，只替换输入获取层

---

### Task 1: 安装 prompt_toolkit

**Files:**
- Modify: （无代码修改，仅 pip install）

- [ ] **Step 1: 安装依赖**

```bash
pip install prompt_toolkit
```

Expected:
```
Successfully installed prompt_toolkit-<version>...
```

- [ ] **Step 2: 验证安装**

```bash
python -c "from prompt_toolkit import PromptSession; from prompt_toolkit.completion import WordCompleter; print('OK')"
```

Expected: `OK`

### Task 2: 替换 input() 为 PromptSession 实现 Tab 补全

**Files:**
- Modify: `cli/cli.py` — 导入、构造 completer/session、替换 input 调用

**Interfaces:**
- Consumes: `cli/cli.py:Cli.__init__`, `Cli.run()` — 现有方法签名
- Produces: 无 — 纯替换，不对外暴露新接口

- [ ] **Step 1: 在 cli/cli.py 文件顶部添加导入**

在现有导入下方添加：

```python
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
```

- [ ] **Step 2: 在 Cli.__init__ 构造 completer 和 session**

在 `self.runner = AgentRunner()` 之后添加：

```python
self._completer = WordCompleter(
    ["/new", "/list", "/switch", "/context", "/compact",
     "/soul", "/skills", "/memory", "/search",
     "/prompt", "/bootstrap", "/help", "/quit", "/exit"],
    ignore_case=True,
)
self._session = PromptSession(completer=self._completer)
```

- [ ] **Step 3: 替换 run() 中的 input() 调用**

原代码第 55 行：
```python
user_input = input(colored_prompt()).strip()
```

改为：
```python
user_input = self._session.prompt(colored_prompt()).strip()
```

- [ ] **Step 4: 手动验证 Tab 补全**

```bash
python ultimate.py chat
```

在 REPL 中测试以下场景：

| 操作 | 期望 |
|------|------|
| 输入 `/` 后按 Tab | 补全列表弹出，显示全部 14 个命令 |
| 输入 `/s` 后按 Tab | 列表过滤，仅显示 search / soul / skills / switch |
| 按 Tab 选择一个命令 | 命令文本填入输入行 |
| 输入普通文本后按 Tab | 无补全，无异常 |
| Ctrl+C | 退出（KeyboardInterrupt 由外层处理） |
| 上下方向键 | 翻查历史命令 |

- [ ] **Step 5: Commit**

```bash
git add cli/cli.py
git commit -m "feat: add Tab completion for REPL commands using prompt_toolkit

Replace input() with PromptSession + WordCompleter so / commands
get Tab completion. 14 built-in commands supported, skill name
completion deferred to future version.

Co-Authored-By: Claude <noreply@anthropic.com>"
```
