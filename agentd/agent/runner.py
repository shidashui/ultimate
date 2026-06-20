# agentd/agent/runner.py
import logging
from agentd.bootstrap import container as _container
from agentd.context.session import SessionStore
from agentd.context.context import ContextGuard
from agentd.memory.memory import MemoryStore
from agentd.skill.skill import SkillsManager
from agentd.prompt.prompts import build_system_prompt

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    Cli 和 Gateway 共用的 LLM 循环核心。

    职责：memory recall → build prompt → LLM call → tool loop → save → return text
    不管：如何获取输入、如何展示/发送输出（由调用方决定）

    调用方持有 messages 和 store，以引用形式传入，runner 直接修改。
    """

    def __init__(self):
        self.container    = _container
        self.guard: ContextGuard  = _container.get("guard")
        self.memory_store: MemoryStore  = _container.get("memory_store")
        self.bootstrap_data: dict       = _container.get("bootstrap_data")
        self.skills_mgr: SkillsManager  = _container.get("skills_mgr")
        self.skills_block: str          = self.skills_mgr.format_prompt_block()
        
    # ── 工具调用 ──────────────────────────────────
    def process_tool_call(self, tool_name: str, tool_input: dict) -> str:
        handler = self.container.tools_handlers.get(tool_name)
        if handler is None:
            return f"Error: Unknown tool '{tool_name}'"
        try:
            return handler(**tool_input)
        except TypeError as exc:
            return f"Error: Invalid arguments for {tool_name}: {exc}"
        except Exception as exc:
            return f"Error: {tool_name} failed: {exc}"

    # ── 公共序列化逻辑 ────────────────────────────
    @staticmethod
    def _serialize(response) -> list[dict]:
        result = []
        for block in response.content:
            if hasattr(block, "text"):
                result.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                result.append({
                    "type": "tool_use",
                    "id":    block.id,
                    "name":  block.name,
                    "input": block.input,
                })
        return result

    @staticmethod
    def _extract_text(response) -> str:
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )

    @staticmethod
    def _rollback(messages: list[dict]) -> None:
        """出错时回滚到最近的 user 消息"""
        while messages and messages[-1]["role"] != "user":
            messages.pop()
        if messages:
            messages.pop()

    # ── 同步版本（Cli 使用）──────────────────────
    def run_turn(
        self,
        user_input: str,
        messages: list[dict],
        store: SessionStore,
        channel: str = "terminal",
    ) -> str:
        """
        返回 assistant 文本回复，出错返回空字符串。
        """
        memory_context = self.memory_store._auto_recall(user_input)

        system_prompt = build_system_prompt(
            mode="full",
            bootstrap=self.bootstrap_data,
            skills_block=self.skills_block,
            memory_context=memory_context,
            channel=channel,
        )

        messages.append({"role": "user", "content": user_input})
        store.save_turn("user", user_input)

        while True:
            try:
                response = self.guard.guard_api_call(
                    system=system_prompt,
                    messages=messages,
                    tools=self.container.tools,
                )
            except Exception as exc:
                logger.exception("[Runner] LLM 调用异常: %s", exc)
                self._rollback(messages)
                return ""

            messages.append({"role": "assistant", "content": response.content})
            store.save_turn("assistant", self._serialize(response))

            if response.stop_reason == "end_turn":
                return self._extract_text(response)

            elif response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = self.process_tool_call(block.name, block.input)
                    store.save_tool_result(block.id, block.name, block.input, result)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })
                messages.append({"role": "user", "content": tool_results})

            else:
                logger.info("[Runner] stop_reason=%s", response.stop_reason)
                return self._extract_text(response)

    # ── 异步版本（Gateway 使用）──────────────────
    async def async_run_turn(
        self,
        user_input: str,
        messages: list[dict],
        store: SessionStore,
        channel: str = "unknown",
    ) -> str:
        """
        async_guard_api_call 原生异步，不阻塞事件循环。
        返回 assistant 文本回复，出错返回空字符串。
        """
        memory_context = self.memory_store._auto_recall(user_input)

        system_prompt = build_system_prompt(
            mode="full",
            bootstrap=self.bootstrap_data,
            skills_block=self.skills_block,
            memory_context=memory_context,
            channel=channel,
        )

        messages.append({"role": "user", "content": user_input})
        store.save_turn("user", user_input)

        while True:
            try:
                response = await self.guard.async_guard_api_call(
                    system=system_prompt,
                    messages=messages,
                    tools=self.container.tools,
                )
            except Exception as exc:
                logger.exception("[Runner] LLM 调用异常: %s", exc)
                self._rollback(messages)
                return ""

            messages.append({"role": "assistant", "content": response.content})
            store.save_turn("assistant", self._serialize(response))

            if response.stop_reason == "end_turn":
                return self._extract_text(response)

            elif response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = self.process_tool_call(block.name, block.input)
                    store.save_tool_result(block.id, block.name, block.input, result)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })
                messages.append({"role": "user", "content": tool_results})

            else:
                logger.info("[Runner] stop_reason=%s", response.stop_reason)
                return self._extract_text(response)