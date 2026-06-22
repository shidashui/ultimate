---
change: cli-skill-routing
design-doc: docs/superpowers/specs/2026-06-22-cli-skill-routing-design.md
base-ref: d92f1454937bd5de2a48a5a8c093e42d6e8fb967
---

# CLI Skill Routing 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户键入 `/技能名` 时 CLI 层识别技能、显示反馈、交给 AI 执行

**Architecture:** CLI 层在硬编码命令之后做动态技能匹配，命中后返回 False 让输入流入 run_turn()，AI 从 system prompt 的 skill_registry 中识别技能并调用 skill_invoke 工具拉取 body

**Tech Stack:** Python 3, prompt_toolkit (WordCompleter, PromptSession), rich (console.print)

## Global Constraints

- 不修改 `run_turn()` 接口，复用 Hermes 现有 skill_invoke 工具链
- 硬编码命令优先于动态技能匹配
- 所有改动仅在 `cli/cli.py` 的 `Cli` 类中

---

### Task 1: 动态 Tab 补全

**Files:**
- Modify: `cli/cli.py:20-25`

**Interfaces:**
- Consumes: `self.runner.skills_mgr.skills[*].invocation`（AgentRunner 初始化完成后）
- Produces: `self._completer` 包含所有技能调用名

- [ ] **Step 1: 将 completer 初始化从 `__init__` 移到 `init_run`**

`WordCompleter` 在 `__init__` 中创建时 `self.runner` 尚未初始化（`self.runner = AgentRunner()` 在前，但 `skills_mgr.discover()` 在 `AgentRunner.__init__()` 之后的 container 初始化中）。将 completer 构建移到 `init_run()` 中，此时 `self.runner.skills_mgr.skills` 已可用。

修改 `__init__`：移除 `self._completer` 和 `self._session` 中的 completer 赋值，`_session` 延迟设置 completer。

修改 `init_run`：在用户输入名字之前构建 completer 和 session。

```python
# __init__: 移除 self._completer 和 self._session 初始化
def __init__(self):
    self.store = SessionStore(base_dir=WORKSPACE_DIR, agent_id="zero")
    self.messages: list[dict] = []
    self.runner = AgentRunner()

# init_run: 在 self.runner 就绪后构建 completer
def init_run(self):
    # 构建动态补全列表
    commands = ["/new", "/list", "/switch", "/context", "/compact",
                "/soul", "/skills", "/memory", "/search",
                "/prompt", "/bootstrap", "/help", "/quit", "/exit"]
    # 追加技能调用名
    for skill in self.runner.skills_mgr.skills:
        inv = skill.get("invocation", "")
        if inv and inv not in commands:
            commands.append(inv)
    self._completer = WordCompleter(commands, ignore_case=True)
    self._session = PromptSession(completer=self._completer)

    user_name = input("请输入你的名字: ").strip() or "User"
    # ... 后续不变
```

- [ ] **Step 2: 验证补全包含技能名**

启动 REPL，输入 `/com` + Tab，应补全为 `/comet`（若 comet skill 存在）。

- [ ] **Step 3: 提交**

```bash
git add cli/cli.py
git commit -m "feat: dynamic tab completion from skills_mgr"
```

- [ ] **Step 4: 同步勾选 tasks.md**

将 `openspec/changes/cli-skill-routing/tasks.md` 中 Task 1 勾选为 `[x]`。

---

### Task 2: 技能路由

**Files:**
- Modify: `cli/cli.py:272`（`return False` 之前）

**Interfaces:**
- Consumes: `self.runner.skills_mgr.skills`（Task 1 已验证可用）
- Produces: 无新接口，命中后 `return False` 使输入流入 `run_turn()`

- [ ] **Step 1: 在 `handle_repl_command` 末尾增加动态技能匹配**

在 `return False` 之前插入：

```python
        # ── 动态技能匹配 ────────────────────────────
        for skill in self.runner.skills_mgr.skills:
            if cmd == skill.get("invocation", ""):
                print_section(f"技能: {skill['name']}")
                console.print(f"  [muted]{skill['description']}[/muted]")
                return False  # 交给 AI，AI 从 skill_registry 识别并调用 skill_invoke

        return False
```

完整上下文（`handle_repl_command` 末尾）：

```python
        elif cmd == "/help":
            # ... 帮助输出逻辑不变 ...
            return True

        # ── 动态技能匹配 ────────────────────────────
        for skill in self.runner.skills_mgr.skills:
            if cmd == skill.get("invocation", ""):
                print_section(f"技能: {skill['name']}")
                console.print(f"  [muted]{skill['description']}[/muted]")
                return False  # 交给 AI，AI 从 skill_registry 识别并调用 skill_invoke

        return False
```

- [ ] **Step 2: 验证路由**

启动 REPL，输入 `/comet test`：
- 应看到 "技能: comet" 及描述
- AI 应按照 comet skill 指令执行

- [ ] **Step 3: 提交**

```bash
git add cli/cli.py
git commit -m "feat: skill routing in handle_repl_command"
```

- [ ] **Step 4: 同步勾选 tasks.md**

将 `openspec/changes/cli-skill-routing/tasks.md` 中 Task 2 勾选为 `[x]`。

---

### Task 3: /help 集成

**Files:**
- Modify: `cli/cli.py:249-271`（`/help` handler）

**Interfaces:**
- Consumes: `self.runner.skills_mgr.skills[*].invocation`、`name`、`description`
- Produces: `/help` 输出追加"可用技能"段

- [ ] **Step 1: 在 `/help` 的 Table 后追加技能列表**

在 `console.print(help_table)` 之后、`return True` 之前插入：

```python
            console.print()
            console.print(Rule(title="可用技能", style="accent"))
            if self.runner.skills_mgr.skills:
                for skill in self.runner.skills_mgr.skills:
                    inv = skill.get("invocation", "")
                    name = skill.get("name", "")
                    desc = skill.get("description", "")
                    console.print(f"  [info]{inv}[/info]  {name} — [muted]{desc}[/muted]")
            else:
                console.print("  [muted](无可用技能)[/muted]")
```

完整上下文（`/help` handler）：

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
            # ── 可用技能段 ────────────────────────────
            console.print()
            console.print(Rule(title="可用技能", style="accent"))
            if self.runner.skills_mgr.skills:
                for skill in self.runner.skills_mgr.skills:
                    inv = skill.get("invocation", "")
                    name = skill.get("name", "")
                    desc = skill.get("description", "")
                    console.print(f"  [info]{inv}[/info]  {name} — [muted]{desc}[/muted]")
            else:
                console.print("  [muted](无可用技能)[/muted]")
            return True
```

- [ ] **Step 2: 验证 /help 输出**

启动 REPL，输入 `/help`：
- 应看到 REPL 命令表格
- 下方应有"可用技能"段，列出所有已发现技能

- [ ] **Step 3: 提交**

```bash
git add cli/cli.py
git commit -m "feat: show available skills in /help"
```

- [ ] **Step 4: 同步勾选 tasks.md**

将 `openspec/changes/cli-skill-routing/tasks.md` 中 Task 3 勾选为 `[x]`。

---

## 完成验证

全部 3 个任务提交后：

```bash
# 确认文件改动
git diff --stat d92f1454937bd5de2a48a5a8c093e42d6e8fb967...HEAD
# 预期: 仅 cli/cli.py 被修改

# 确认 tasks.md 全部勾选
grep -c '\[x\]' openspec/changes/cli-skill-routing/tasks.md
# 预期: 3
```
