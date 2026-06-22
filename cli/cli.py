import asyncio
import json
from utils.print_tools import *
from rich.markdown import Markdown
from config.configs import MAX_TOTAL_CHARS, MODEL, WORKSPACE_DIR

from agentd.context.session import SessionStore
from agentd.prompt.prompts import build_system_prompt
from agentd.agent.runner import AgentRunner

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter


class Cli:
    def __init__(self):
        self.store = SessionStore(base_dir=WORKSPACE_DIR, agent_id="zero")
        self.messages: list[dict] = []
        self.runner = AgentRunner()
        self._completer = WordCompleter(
            ["/new", "/list", "/switch", "/context", "/compact",
             "/soul", "/skills", "/memory", "/search",
             "/prompt", "/bootstrap", "/help", "/quit", "/exit"],
            ignore_case=True,
        )
        self._session = PromptSession(completer=self._completer)

    def init_run(self):
        user_name = input("请输入你的名字: ").strip() or "User"
        self.store.set_user_name(user_name)

        # 恢复最近的会话或创建新会话
        sessions = self.store.list_sessions()
        if sessions:
            sid = sessions[0][0]
            self.messages = self.store.load_session(sid)
            print_session(f"  恢复会话: {sid} ({len(self.messages)} 条消息)")
        else:
            sid = self.store.create_session("initial")
            self.messages = []
            print_session(f"  创建新会话: {sid}")

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
        console.print()
        print_assistant(f"你好{user_name}！我是你的智能助理。有什么我可以帮你的吗？")

    def run(self):
        """
        从命令行接收用户输入，并生成聊天事件
        """
        self.init_run()
        while True:
            try:
                user_input = self._session.prompt(colored_prompt()).strip()
            except (KeyboardInterrupt, EOFError):
                print_info("退出系统。")
                break
            if user_input.lower() in ('/exit', '/quit'):  # 用户输入 '/exit' 或 '/quit' 则退出
                print_info("退出系统。")
                break

            # 获取处理结果
            self.handle_user_input(user_input)
    
    def handle_user_input(self, user_input: str):
        if user_input.startswith("/") and self.handle_repl_command(user_input):
            return
        reply = asyncio.run(
            self.runner.run_turn(
                user_input=user_input,
                messages=self.messages,
                store=self.store,
                channel="terminal",
            )
        )
        if reply:
            console.print()
            console.print("Assistant:", style="success", end=" ")
            console.print(Markdown(reply))
    
    def handle_repl_command(self, command: str) -> bool:
        """
        处理以 / 开头的命令。
        返回 (是否已处理)。
        """

        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/new":
            label = arg or ""
            sid = self.store.create_session(label)
            self.messages.clear()
            print_session(f"  Created new session: {sid}" + (f" ({label})" if label else ""))
            return True

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

        elif cmd == "/switch":
            if not arg:
                print_warn("  Usage: /switch <session_id>")
                return True
            target_id = arg.strip()
            matched = [sid for sid in self.store._index if sid.startswith(target_id)]
            if len(matched) == 0:
                print_warn(f"  Session not found: {target_id}")
                return True
            if len(matched) > 1:
                print_warn(f"  Ambiguous prefix, matches: {', '.join(matched)}")
                return True
            sid = matched[0]
            self.messages = self.store.load_session(sid)
            print_session(f"  Switched to session: {sid} ({len(self.messages)} messages)")
            return True

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

        elif cmd == "/compact":
            if len(self.messages) <= 4:
                print_info("  Too few messages to compact (need > 4).")
                return True
            print_session("  Compacting history...")
            new_messages = self.runner.guard.compact_history(self.messages)
            print_session(f"  {len(self.messages)} -> {len(new_messages)} messages")
            self.messages = new_messages
            return True
        
        elif cmd == "/soul":
            console.print(Rule(title="SOUL.md", style="accent"))
            soul = self.runner.bootstrap_data.get("SOUL.md", "")
            if soul:
                console.print(soul)
            else:
                console.print("[muted](未找到 SOUL.md)[/muted]")
            return True

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

        elif cmd == "/memory":
            stats = self.runner.memory_store.get_stats()
            mem_text = (
                f"  长期记忆 (MEMORY.md): {stats['evergreen_chars']} 字符\n"
                f"  每日文件: {stats['daily_files']}\n"
                f"  每日条目: {stats['daily_entries']}"
            )
            console.print(Panel(mem_text, title="记忆统计", border_style="accent"))
            return True

        elif cmd == "/search":
            if not arg:
                print_yellow_info("用法: /search <query>")
                return True
            print_section(f"记忆搜索: {arg}")
            results = self.runner.memory_store.hybrid_search(arg)
            if not results:
                print_info("(无结果)")
            else:
                for r in results:
                    print_memory_info(r)
            return True

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
        
        return False
