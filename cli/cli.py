import asyncio
import json
from utils.print_tools import *
from config.configs import MAX_TOTAL_CHARS, MODEL, WORKSPACE_DIR

from agentd.context.session import SessionStore
from agentd.prompt.prompts import build_system_prompt
from agentd.agent.runner import AgentRunner


class Cli:
    def __init__(self):
        self.store = SessionStore(base_dir=WORKSPACE_DIR, agent_id="zero")
        self.messages: list[dict] = []
        self.runner = AgentRunner()

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
        print()

        print_assistant(f"你好{user_name}！我是你的智能助理。有什么我可以帮你的吗？")

    def run(self):
        """
        从命令行接收用户输入，并生成聊天事件
        """
        self.init_run()
        while True:
            try:
                user_input = input(colored_prompt()).strip()
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
            print_assistant(reply)
    
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
                print_info("  No sessions found.")
                return True
            print_info("  Sessions:")
            for sid, meta in sessions:
                active = " <-- current" if sid == self.store.current_session_id else ""
                label = meta.get("label", "")
                label_str = f" ({label})" if label else ""
                count = meta.get("message_count", 0)
                last = meta.get("last_active", "?")[:19]
                print_info(f"    {sid}{label_str}  msgs={count}  last={last}{active}")
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
            print_info(f"  Context usage: ~{estimated:,} / {self.runner.guard.max_tokens:,} tokens")
            print_context(pct, bar)
            print_info(f"  Messages: {len(self.messages)}")
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
            print_section("SOUL.md")
            soul = self.runner.bootstrap_data.get("SOUL.md", "")
            print(soul) if soul else print_info("(未找到 SOUL.md)")
            return True

        elif cmd == "/skills":
            print_section("已发现的技能")
            if not self.runner.skills_mgr.skills:
                print_info("(未发现技能)")
            else:
                for s in self.runner.skills_mgr.skills:
                    print_tool_info(s)
            return True

        elif cmd == "/memory":
            print_section("记忆统计")
            stats = self.runner.memory_store.get_stats()
            print(f"  长期记忆 (MEMORY.md): {stats['evergreen_chars']} 字符")
            print(f"  每日文件: {stats['daily_files']}")
            print(f"  每日条目: {stats['daily_entries']}")
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
            print_section("完整系统提示词")
            prompt = build_system_prompt(
                mode="full", bootstrap=self.runner.bootstrap_data,
                skill_registry=self.runner.skill_registry,
                channel="terminal",
            )
            if len(prompt) > 3000:
                print(prompt[:3000] + "\n")
                print_info(f"... ({len(prompt) - 3000} more chars, total {len(prompt)})")
            else:
                print(prompt)
            print_info(f"提示词总长度: {len(prompt)} 字符")
            return True

        elif cmd == "/bootstrap":
            print_section("Bootstrap 文件")
            if not self.runner.bootstrap_data:
                print_info("(未加载 Bootstrap 文件)")
            else:
                for name, content in self.runner.bootstrap_data.items():
                    print(f"  {BLUE}{name}{RESET}: {len(content)} chars")
            total = sum(len(v) for v in self.runner.bootstrap_data.values())
            print(f"\n  {DIM}总计: {total} 字符 (上限: {MAX_TOTAL_CHARS}){RESET}")
            return True
        
        elif cmd == "/help":
            print_info("  Commands:")
            print_info("    /new [label]       Create a new session")
            print_info("    /list              List all sessions")
            print_info("    /switch <id>       Switch to a session (prefix match)")
            print_info("    /context           Show context token usage")
            print_info("    /compact           Manually compact conversation history")
            print_info("    /soul              Show SOUL.md content")
            print_info("    /skills            List discovered skills")
            print_info("    /memory            Show memory stats")
            print_info("    /search <query>    Search memory with a query")
            print_info("    /prompt            Show the full system prompt")
            print_info("    /bootstrap         Show loaded Bootstrap files")
            print_info("    /help              Show this help")
            print_info("    /quit /exit        Exit the REPL")
            return True
        
        return False
