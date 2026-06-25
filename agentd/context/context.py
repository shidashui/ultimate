import asyncio
import json
from collections.abc import Callable
from typing import Any
from config.configs import CONTEXT_SAFE_LIMIT
from utils.print_tools import print_session, print_warn
from agentd.providers.base import ErrorType, ProviderError
from agentd.providers.error_mapper import classify


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

    PREFLIGHT_RATIO = 0.8  # 80% 阈值触发预飞压缩

    def __init__(self, max_tokens: int = CONTEXT_SAFE_LIMIT, provider=None,
                 provider_router=None):
        self.max_tokens = max_tokens
        self._provider = provider  # backward compat
        self._router = provider_router  # new: ProviderRouter

    def _get_provider(self):
        """返回当前活跃的 provider（优先 router，回退到单 provider）。"""
        if self._router is not None:
            return self._router.current
        if self._provider is not None:
            return self._provider
        raise RuntimeError("No provider configured")

    def estimate_tokens(self, text: str) -> int:
        try:
            return self._get_provider().estimate_tokens(text)
        except RuntimeError:
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

    async def preflight(self, system: str, messages: list[dict]) -> list[dict]:
        """预飞检查：估算 token 总量，超阈值主动压缩后返回。

        不超阈值时返回原 messages（零开销）。
        压缩失败时返回原 messages（让反应式重试兜底）。
        """
        total = self.estimate_tokens(system) + self.estimate_messages_tokens(messages)
        if total > self.max_tokens * self.PREFLIGHT_RATIO:
            print_warn(
                f"  [preflight] ~{total:,} tokens "
                f"(>{self.PREFLIGHT_RATIO*100:.0f}% threshold), compacting..."
            )
            try:
                return await self.compact_history(messages)
            except Exception as exc:
                print_warn(f"  [preflight] compact failed: {exc}, skipping")
                return messages
        return messages

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

    async def compact_history(self, messages: list[dict]) -> list[dict]:
        """将前 50% 的消息压缩为 LLM 生成的摘要。"""
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
            summary_resp = await self._get_provider().chat(
                messages=[{"role": "user", "content": summary_prompt}],
                system="You are a conversation summarizer. Be concise and factual.",
                max_tokens=2048,
            )
            summary_text = "".join(
                block.text for block in summary_resp.content if block.type == "text"
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

    async def async_guard_api_call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> Any:
        """
        类型化错误重试调度:

          CONTEXT_OVERFLOW  → 截断工具结果 → 压缩历史 → 抛出
          RATE_LIMIT        → 指数退避 (1s, 2s, 4s) → 抛出
          AUTH_FAILURE      → 切换 provider → 重试 / 抛出
          SERVER_ERROR      → 线性退避 (2s, 4s) → 抛出
          TIMEOUT           → 增加超时 (30→60→120s) → 抛出
          MODEL_UNAVAILABLE → 切换 provider → 重试 / 抛出
          UNKNOWN           → 立即抛出，不重试
        """
        current_messages = messages
        timeout_s = 30

        # 上下文溢出专用的两次重试计数器（与其他错误类型独立）
        overflow_attempt = 0

        for attempt in range(5):  # 安全上限: 总重试不超过 5 次
            provider = self._get_provider()
            try:
                result = await provider.chat(
                    messages=current_messages,
                    system=system,
                    tools=tools,
                    max_tokens=8096,
                    timeout=timeout_s,
                )

                if current_messages is not messages:
                    messages.clear()
                    messages.extend(current_messages)
                return result

            except Exception as exc:
                err = classify(exc)

                match err.error_type:

                    case ErrorType.CONTEXT_OVERFLOW:
                        if overflow_attempt == 0:
                            print_warn(
                                "  [guard] Context overflow detected, "
                                "truncating large tool results..."
                            )
                            current_messages = self._truncate_large_tool_results(current_messages)
                            overflow_attempt += 1
                        elif overflow_attempt == 1:
                            print_warn(
                                "  [guard] Still overflowing, "
                                "compacting conversation history..."
                            )
                            current_messages = await self.compact_history(current_messages)
                            overflow_attempt += 1
                        else:
                            raise

                    case ErrorType.RATE_LIMIT:
                        if attempt < 3:
                            wait = 2 ** attempt  # 1s, 2s, 4s
                            print_warn(
                                f"  [guard] Rate limited ({err.status_code}), "
                                f"waiting {wait}s..."
                            )
                            await asyncio.sleep(wait)
                        else:
                            raise

                    case ErrorType.AUTH_FAILURE:
                        if self._router is not None and self._router.switch():
                            new_model = self._router.current._model
                            print_warn(
                                f"  [guard] Auth failure, switched to {new_model}"
                            )
                        else:
                            raise

                    case ErrorType.SERVER_ERROR:
                        if attempt < 2:
                            wait = 2 * (attempt + 1)  # 2s, 4s
                            print_warn(
                                f"  [guard] Server error ({err.status_code}), "
                                f"retrying in {wait}s..."
                            )
                            await asyncio.sleep(wait)
                        else:
                            raise

                    case ErrorType.TIMEOUT:
                        if attempt < 2:
                            timeout_s = [60, 120, 180][attempt]
                            print_warn(
                                f"  [guard] Request timeout, "
                                f"increasing to {timeout_s}s..."
                            )
                        else:
                            raise

                    case ErrorType.MODEL_UNAVAILABLE:
                        if self._router is not None and self._router.switch():
                            new_model = self._router.current._model
                            print_warn(
                                f"  [guard] Model unavailable, "
                                f"switched to {new_model}"
                            )
                        else:
                            raise

                    case ErrorType.UNKNOWN:
                        raise

        raise RuntimeError("async_guard_api_call: exhausted all retries")

    async def async_guard_stream_call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> Any:
        """
        Streaming 路径的 guard 保护:

          CONTEXT_OVERFLOW  → 截断工具结果 → 压缩历史 → 抛出
          AUTH_FAILURE      → 切换 provider → 重试 / 抛出
          MODEL_UNAVAILABLE → 切换 provider → 重试 / 抛出
          RATE_LIMIT        → 立即抛出，不重试 (chunks 可能已发出)
          SERVER_ERROR      → 立即抛出，不重试
          TIMEOUT           → 立即抛出，不重试
        """
        current_messages = messages
        timeout_s = 30
        overflow_attempt = 0

        for attempt in range(3):  # 安全上限
            provider = self._get_provider()
            try:
                # 预飞压缩 — 在 stream 建立前执行
                current_messages = await self.preflight(system, current_messages)

                return await provider.chat_stream(
                    messages=current_messages,
                    system=system,
                    tools=tools,
                    on_text_chunk=on_chunk,
                    timeout=timeout_s,
                )

            except Exception as exc:
                err = classify(exc)

                # CONTEXT_OVERFLOW: 安全保留 — 在 stream 建立前检测
                if err.error_type == ErrorType.CONTEXT_OVERFLOW:
                    if overflow_attempt == 0:
                        print_warn(
                            "  [guard:stream] Context overflow detected, "
                            "truncating large tool results..."
                        )
                        current_messages = self._truncate_large_tool_results(current_messages)
                        overflow_attempt += 1
                    elif overflow_attempt == 1:
                        print_warn(
                            "  [guard:stream] Still overflowing, "
                            "compacting conversation history..."
                        )
                        current_messages = await self.compact_history(current_messages)
                        overflow_attempt += 1
                    else:
                        raise

                # AUTH / MODEL 切换: 安全重试 — 连接级
                elif err.error_type in (ErrorType.AUTH_FAILURE,
                                         ErrorType.MODEL_UNAVAILABLE):
                    if self._router is not None and self._router.switch():
                        new_model = self._router.current._model
                        print_warn(
                            f"  [guard:stream] Auth/model unavailable, "
                            f"switched to {new_model}"
                        )
                        continue
                    raise

                # RATE_LIMIT / SERVER_ERROR / TIMEOUT: 不重试
                else:
                    raise

        raise RuntimeError("async_guard_stream_call: exhausted all retries")
