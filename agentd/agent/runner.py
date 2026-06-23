# agentd/agent/runner.py
import logging
from datetime import datetime, timezone
from agentd.bootstrap import Container, set_current_container
from agentd.context.session import SessionStore
from agentd.context.context import ContextGuard
from agentd.memory.memory import MemoryStore
from agentd.skill.skill import SkillsManager
from agentd.prompt.prompts import build_system_prompt
from agentd.agent.budget import IterationBudget
from agentd.providers.base import ErrorType, ProviderError
from config.configs import MAX_TOOL_ITERATIONS
from agentd.tools.param_repair import validate_and_repair
from agentd.tools.audit import AuditRecord, AuditLogger
import time as _time

logger = logging.getLogger(__name__)


class AgentRunner:
    """
    Cli 和 Gateway 共用的 LLM 循环核心（统一异步入口）。

    职责：memory recall → build/cache prompt → preflight → LLM call → tool loop → save → return text
    不管：如何获取输入、如何展示/发送输出（由调用方决定）

    调用方持有 messages 和 store，以引用形式传入，runner 直接修改。
    """

    def __init__(self, session_id: str | None = None):
        self.container = Container(session_id=session_id)
        self.guard: ContextGuard  = self.container.get("guard")
        self.memory_store: MemoryStore  = self.container.get("memory_store")
        self.bootstrap_data: dict       = self.container.get("bootstrap_data")
        self.skills_mgr: SkillsManager  = self.container.get("skills_mgr")
        self.skill_registry: str        = self.skills_mgr.format_skill_registry()
        self.max_iterations: int        = MAX_TOOL_ITERATIONS

        # System prompt 缓存 — 首次构建，跨轮复用
        self._cached_system_prompt: str | None = None

    # ── 便捷属性（避免调用方越级访问 self.container）───
    @property
    def tools_handlers(self) -> dict:
        return self.container.tools_handlers

    @property
    def session_db(self):
        return self.container.get("session_db")

    # ── 工具调用 ──────────────────────────────────
    def process_tool_call(self, tool_name: str, tool_input: dict) -> str:
        handler = self.container.tools_handlers.get(tool_name)
        if handler is None:
            return f"Error: Unknown tool '{tool_name}'"

        # ── 审计：入口 ──
        t_start = _time.perf_counter()
        audit_warnings: list[str] = []
        blocked = False

        # ── 参数校验 + 自动修复 ──
        schema = self.container.tools_schemas.get(tool_name)
        if schema:
            repaired, warnings = validate_and_repair(tool_input, schema, handler)
            for w in warnings:
                logger.warning("[param-repair] %s: %s (original=%s)", tool_name, w, repr(tool_input))
            if not repaired and warnings:
                blocked = True
                result = f"Error: Invalid arguments for {tool_name}: {'; '.join(warnings)}"
                # ── 审计：出口（参数错误）──
                self._audit_log(tool_name, tool_input, result, t_start, audit_warnings, blocked)
                return result
            tool_input = repaired
            # Track repair warnings for audit
            audit_warnings.extend(w for w in warnings if "cannot coerce" not in w)

        # ── 安全网（repair 之后不太可能触发，但保留作为兜底）──
        try:
            result = handler(**tool_input)
        except TypeError as exc:
            result = f"Error: Invalid arguments for {tool_name}: {exc}"
        except Exception as exc:
            result = f"Error: {tool_name} failed: {exc}"

        # Check if this was a blocked call (result starts with "Error: Blocked:")
        if result.startswith("Error: Blocked:"):
            blocked = True

        # ── 审计：出口 ──
        self._audit_log(tool_name, tool_input, result, t_start, audit_warnings, blocked)
        return result

    def _audit_log(
        self, tool_name: str, tool_input: dict, result: str,
        t_start: float, warnings: list[str], blocked: bool,
    ) -> None:
        """Record audit log entry. Never throws."""
        try:
            audit: AuditLogger = self.container.get("audit_logger")
            if audit is None:
                return
            duration_ms = (_time.perf_counter() - t_start) * 1000
            result_summary = result[:200] if result else ""
            audit.log(AuditRecord(
                tool_name=tool_name,
                params=tool_input,
                result_summary=result_summary,
                duration_ms=duration_ms,
                warnings=warnings,
                blocked=blocked,
            ))
        except Exception:
            pass  # audit failure must not affect tool execution

    # ── 公共序列化逻辑 ────────────────────────────
    @staticmethod
    def _serialize(response) -> list[dict]:
        result = []
        for block in response.content:
            if block.type == "text":
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
            block.text for block in response.content if block.type == "text"
        )

    @staticmethod
    def _rollback(messages: list[dict]) -> None:
        """出错时回滚到最近的 user 消息"""
        while messages and messages[-1]["role"] != "user":
            messages.pop()
        if messages:
            messages.pop()

    # ── 统一异步入口 ─────────────────────────────
    async def run_turn(
        self,
        user_input: str,
        messages: list[dict],
        store: SessionStore,
        channel: str = "terminal",
    ) -> str:
        """
        返回 assistant 文本回复，出错返回空字符串。

        CLI 端通过 asyncio.run() 调用，Gateway 端直接 await。
        """
        set_current_container(self.container)
        try:
            # 0. 重置 provider 到主（每 turn 重新开始）
            provider_router = self.container.get("provider_router")
            if provider_router:
                provider_router.reset()

            # 1. 记忆召回
            memory_context = self.memory_store._auto_recall(user_input)

            # 2. System prompt 缓存：首次构建，后续复用
            if self._cached_system_prompt is None:
                self._cached_system_prompt = build_system_prompt(
                    mode="full",
                    bootstrap=self.bootstrap_data,
                    skill_registry=self.skill_registry,
                    channel=channel,
                )

            # 3. 记忆上下文 + 时间戳注入 user message
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            parts = [f"[系统时间: {now}]"]
            if memory_context:
                parts.append(f"[记忆上下文]\n{memory_context}")
            parts.append(f"[用户消息]\n{user_input}")
            user_content = "\n\n".join(parts)

            messages.append({"role": "user", "content": user_content})
            store.save_turn("user", user_input)

            # 4. 工具循环（含迭代预算 + 预飞压缩）
            budget = IterationBudget(self.max_iterations)
            last_response = None

            while budget.remaining > 0:
                budget.consume()

                # 预飞压缩：主动检查 token，超阈值先压缩
                messages = await self.guard.preflight(self._cached_system_prompt, messages)

                try:
                    response = await self.guard.async_guard_api_call(
                        system=self._cached_system_prompt,
                        messages=messages,
                        tools=self.container.tools,
                    )
                    last_response = response
                except ProviderError as exc:
                    # 不可恢复错误 — 明确报错给用户
                    if exc.error_type in (ErrorType.AUTH_FAILURE,
                                           ErrorType.MODEL_UNAVAILABLE):
                        logger.error("[Runner] 不可恢复错误: %s (type=%s)",
                                     exc, exc.error_type.value)
                        self._rollback(messages)
                        return (f"抱歉，服务暂时不可用。\n"
                                f"  原因: {exc}\n"
                                f"  请检查 API Key 配置或稍后重试。")
                    # 可恢复但已耗尽重试
                    logger.exception("[Runner] LLM 调用失败 (重试耗尽): %s", exc)
                    self._rollback(messages)
                    return ""
                except Exception as exc:
                    logger.exception("[Runner] LLM 调用异常: %s", exc)
                    self._rollback(messages)
                    return ""

                messages.append({"role": "assistant", "content": self._serialize(response)})
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

            # 预算耗尽 — 返回最后一条 assistant 文本
            if last_response:
                return self._extract_text(last_response)
            return "已达到工具调用上限，对话终止。"
        finally:
            set_current_container(None)
