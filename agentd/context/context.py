import json
from typing import Any
from anthropic import Anthropic
from config.configs import CONTEXT_SAFE_LIMIT
from utils.print_tools import print_session, print_warn
from utils.clients import message_client, message_client_stream, async_message_client
import asyncio


def _serialize_messages_for_summary(messages: list[dict]) -> str:
    """将消息列表扁平化为纯文本, 用于 LLM 摘要。"""
    parts: list[str] = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "text":
                        parts.append(f"[{role}]: {block['text']}")
                    elif btype == "tool_use":
                        parts.append(
                            f"[{role} called {block.get('name', '?')}]: "
                            f"{json.dumps(block.get('input', {}), ensure_ascii=False)}"
                        )
                    elif btype == "tool_result":
                        rc = block.get("content", "")
                        preview = rc[:500] if isinstance(rc, str) else str(rc)[:500]
                        parts.append(f"[tool_result]: {preview}")
                elif hasattr(block, "text"):
                    parts.append(f"[{role}]: {block.text}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# ContextGuard -- 上下文溢出保护
# ---------------------------------------------------------------------------
# 三个阶段:
#   1. 截断过大的工具结果 (在换行边界处只保留头部)
#   2. 将旧消息压缩为 LLM 生成的摘要 (固定 50% 比例)
#   3. 仍然溢出则抛出异常
# ---------------------------------------------------------------------------


class ContextGuard:
    """保护 agent 免受上下文窗口溢出。"""

    def __init__(self, max_tokens: int = CONTEXT_SAFE_LIMIT):
        self.max_tokens = max_tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return len(text) // 4

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if "text" in block:
                            total += self.estimate_tokens(block["text"])
                        elif block.get("type") == "tool_result":
                            rc = block.get("content", "")
                            if isinstance(rc, str):
                                total += self.estimate_tokens(rc)
                        elif block.get("type") == "tool_use":
                            total += self.estimate_tokens(
                                json.dumps(block.get("input", {}))
                            )
                    else:
                        if hasattr(block, "text"):
                            total += self.estimate_tokens(block.text)
                        elif hasattr(block, "input"):
                            total += self.estimate_tokens(
                                json.dumps(block.input)
                            )
        return total

    def truncate_tool_result(self, result: str, max_fraction: float = 0.3) -> str:
        """在换行边界处只保留头部进行截断。"""
        max_chars = int(self.max_tokens * 4 * max_fraction)
        if len(result) <= max_chars:
            return result
        cut = result.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        head = result[:cut]
        return head + f"\n\n[... truncated ({len(result)} chars total, showing first {len(head)}) ...]"

    def compact_history(self, messages: list[dict]) -> list[dict]:
        """
        将前 50% 的消息压缩为 LLM 生成的摘要。
        保留最后 N 条消息 (N = max(4, 总数的 20%)) 不变。
        """
        total = len(messages)
        if total <= 4:
            return messages

        keep_count = max(4, int(total * 0.2))
        compress_count = max(2, int(total * 0.5))
        compress_count = min(compress_count, total - keep_count)

        if compress_count < 2:
            return messages

        old_messages = messages[:compress_count]
        recent_messages = messages[compress_count:]

        old_text = _serialize_messages_for_summary(old_messages)

        summary_prompt = (
            "Summarize the following conversation concisely, "
            "preserving key facts and decisions. "
            "Output only the summary, no preamble.\n\n"
            f"{old_text}"
        )

        try:
            summary_resp = message_client(
                max_tokens=2048, 
                system="You are a conversation summarizer. Be concise and factual.", 
                messages=[{"role": "user", "content": summary_prompt}]
            )
            summary_text = ""
            for block in summary_resp.content:
                if hasattr(block, "text"):
                    summary_text += block.text

            print_session(
                f"  [compact] {len(old_messages)} messages -> summary "
                f"({len(summary_text)} chars)"
            )
        except Exception as exc:
            print_warn(f"  [compact] Summary failed ({exc}), dropping old messages")
            return recent_messages

        compacted = [
            {
                "role": "user",
                "content": "[Previous conversation summary]\n" + summary_text,
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Understood, I have the context from our previous conversation."}],
            },
        ]
        compacted.extend(recent_messages)
        return compacted

    async def async_compact_history(self, messages: list[dict]) -> list[dict]:
        total = len(messages)
        if total <= 4:
            return messages

        keep_count     = max(4, int(total * 0.2))
        compress_count = max(2, int(total * 0.5))
        compress_count = min(compress_count, total - keep_count)

        if compress_count < 2:
            return messages

        old_messages    = messages[:compress_count]
        recent_messages = messages[compress_count:]
        old_text        = _serialize_messages_for_summary(old_messages)

        summary_prompt = (
            "Summarize the following conversation concisely, "
            "preserving key facts and decisions. "
            "Output only the summary, no preamble.\n\n"
            f"{old_text}"
        )

        try:
            summary_resp = await async_message_client(
                max_tokens=2048,
                system="You are a conversation summarizer. Be concise and factual.",
                messages=[{"role": "user", "content": summary_prompt}],
            )
            summary_text = "".join(
                block.text for block in summary_resp.content if hasattr(block, "text")
            )
            print_session(
                f"  [compact] {len(old_messages)} messages -> summary "
                f"({len(summary_text)} chars)"
            )
        except Exception as exc:
            print_warn(f"  [compact] Summary failed ({exc}), dropping old messages")
            return recent_messages

        return [
            {
                "role": "user",
                "content": "[Previous conversation summary]\n" + summary_text,
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Understood, I have the context from our previous conversation."}],
            },
            *recent_messages,
        ]

    def _truncate_large_tool_results(self, messages: list[dict]) -> list[dict]:
        """遍历消息列表, 截断过大的 tool_result 块。"""
        result = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                new_blocks = []
                for block in content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_result"
                            and isinstance(block.get("content"), str)):
                        block = dict(block)
                        block["content"] = self.truncate_tool_result(
                            block["content"]
                        )
                    new_blocks.append(block)
                result.append({"role": msg["role"], "content": new_blocks})
            else:
                result.append(msg)
        return result

    def guard_api_call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_retries: int = 2,
    ) -> Any:
        """
        三阶段重试:
          第0次尝试: 正常调用
          第1次尝试: 截断过大的工具结果
          第2次尝试: 通过 LLM 摘要压缩历史
        """
        current_messages = messages

        for attempt in range(max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "max_tokens": 8096,
                    "system": system,
                    "messages": current_messages,
                }
                if tools:
                    kwargs["tools"] = tools
                result = message_client(**kwargs)
                if current_messages is not messages:
                    messages.clear()
                    messages.extend(current_messages)
                return result

            except Exception as exc:
                error_str = str(exc).lower()
                is_overflow = ("context" in error_str or "token" in error_str)

                if not is_overflow or attempt >= max_retries:
                    raise

                if attempt == 0:
                    print_warn(
                        "  [guard] Context overflow detected, "
                        "truncating large tool results..."
                    )
                    current_messages = self._truncate_large_tool_results(
                        current_messages
                    )
                elif attempt == 1:
                    print_warn(
                        "  [guard] Still overflowing, "
                        "compacting conversation history..."
                    )
                    current_messages = self.compact_history(current_messages)

        raise RuntimeError("guard_api_call: exhausted retries")


    def guard_api_call_stream(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_retries: int = 2,
    ):
        current_messages = messages

        for attempt in range(max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "max_tokens": 8096,
                    "system": system,
                    "messages": current_messages,
                }
                if tools:
                    kwargs["tools"] = tools

                # 返回 stream 上下文管理器，由调用方用 with 语句消费
                stream = message_client_stream(**kwargs)

                if current_messages is not messages:
                    messages.clear()
                    messages.extend(current_messages)
                return stream

            except Exception as exc:
                error_str = str(exc).lower()
                is_overflow = ("context" in error_str or "token" in error_str)

                if not is_overflow or attempt >= max_retries:
                    raise

                if attempt == 0:
                    print_warn("  [guard] Context overflow, truncating large tool results...")
                    current_messages = self._truncate_large_tool_results(current_messages)
                elif attempt == 1:
                    print_warn("  [guard] Still overflowing, compacting history...")
                    current_messages = self.compact_history(current_messages)

        raise RuntimeError("guard_api_call: exhausted retries")
    
    async def async_guard_api_call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_retries: int = 2,
    ) -> Any:
        """
        guard_api_call 的异步版本。
        三阶段重试:
          第0次尝试: 正常调用
          第1次尝试: 截断过大的工具结果
          第2次尝试: 通过 LLM 摘要压缩历史
        """
        current_messages = messages

        for attempt in range(max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "max_tokens": 8096,
                    "system": system,
                    "messages": current_messages,
                }
                if tools:
                    kwargs["tools"] = tools

                result = await async_message_client(**kwargs)

                if current_messages is not messages:
                    messages.clear()
                    messages.extend(current_messages)
                return result

            except Exception as exc:
                error_str = str(exc).lower()
                is_overflow = ("context" in error_str or "token" in error_str)

                if not is_overflow or attempt >= max_retries:
                    raise

                if attempt == 0:
                    print_warn(
                        "  [guard] Context overflow detected, "
                        "truncating large tool results..."
                    )
                    current_messages = self._truncate_large_tool_results(current_messages)
                elif attempt == 1:
                    print_warn(
                        "  [guard] Still overflowing, "
                        "compacting conversation history..."
                    )
                    current_messages = await self.async_compact_history(current_messages)

        raise RuntimeError("async_guard_api_call: exhausted retries")