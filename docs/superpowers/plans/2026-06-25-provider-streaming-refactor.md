---
change: provider-streaming-refactor
design-doc: docs/superpowers/specs/2026-06-25-provider-streaming-refactor-design.md
base-ref: 23dcfe29a18ba50da29969c1285a162aebfbfe65
archived-with: 2026-06-25-provider-streaming-refactor
---

# Provider Streaming Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add streaming LLM support to BaseProvider, AnthropicProvider, ContextGuard and AgentRunner while keeping the existing one-shot path unchanged.

**Architecture:** Three-layer change — (1) BaseProvider gains `chat_stream()` abstract method, (2) AnthropicProvider implements it via SDK `messages.stream()`, (3) ContextGuard gains `async_guard_stream_call()` with selective retry, (4) AgentRunner accepts optional `on_text_chunk` callback routing to the new guard method.

**Tech Stack:** Python 3.8+, anthropic SDK, asyncio

## Global Constraints

- Python 3.8+ (no `match`/`case` statements)
- One-shot path: zero changes to existing behavior
- `on_text_chunk` defaults to `None` — all existing callers unaffected
- Streaming retry boundary: only overflow + auth/model errors retry; RATE_LIMIT/SERVER_ERROR/TIMEOUT do not
- ContentBlock normalization shared between `chat()` and `chat_stream()`

archived-with: 2026-06-25-provider-streaming-refactor
---

### Task 1: BaseProvider — Add chat_stream() abstract method

**Files:**
- Modify: `agentd/providers/base.py:24-36`

**Interfaces:**
- Produces: `BaseProvider.chat_stream(messages, system, tools, on_text_chunk, **kwargs) -> Response` (abstract)

- [ ] **Step 1: Add `Callable` import and abstract method**

In `agentd/providers/base.py`, add `Callable` to imports and insert `chat_stream()` between `chat()` and `estimate_tokens()`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from collections.abc import Callable
```

In `BaseProvider` class, after the `chat()` abstract method (line 36, after `...`), add:

```python
    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        system: str | list,
        tools: list[dict] | None = None,
        on_text_chunk: Callable[[str], None] | None = None,
        **kwargs,
    ) -> Response:
        """流式聊天 — 每收到 text chunk 调用 on_text_chunk，最终返回完整 Response。"""
        ...
```

- [ ] **Step 2: Verify the file is valid Python**

Run: `python -c "from agentd.providers.base import BaseProvider; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agentd/providers/base.py
git commit -m "feat: add chat_stream() abstract method to BaseProvider

- Introduces Callable-typed on_text_chunk callback parameter
- Same signature as chat() with additional streaming callback
- Returns Response identically to chat()

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-provider-streaming-refactor
---

### Task 2: AnthropicProvider — Implement chat_stream()

**Files:**
- Modify: `agentd/providers/anthropic.py:17-52`

**Interfaces:**
- Consumes: `BaseProvider.chat_stream()` signature from Task 1
- Produces: `AnthropicProvider.chat_stream()` implementation; `AnthropicProvider._normalize_response(stream_or_message)` private method (`-> Response`)

- [ ] **Step 1: Extract ContentBlock normalization to a private method**

In `agentd/providers/anthropic.py`, extract the block-normalization logic from `chat()` into `_normalize_response()`:

```python
class AnthropicProvider(BaseProvider):
    """封装 anthropic.AsyncAnthropic，输出归一化 Response。"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self._model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
        )

    def _normalize_response(self, result) -> Response:
        """将 Anthropic SDK 消息归一化为 Response。chat 和 chat_stream 共用。"""
        content: list[ContentBlock] = []
        for block in result.content:
            if hasattr(block, "text"):
                content.append(ContentBlock(
                    type="text",
                    text=block.text,
                ))
            elif block.type == "tool_use":
                content.append(ContentBlock(
                    type="tool_use",
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))
        return Response(
            content=content,
            stop_reason=result.stop_reason,
        )

    async def chat(
        self,
        messages: list[dict],
        system: str | list,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Response:
        kwargs.setdefault("max_tokens", 8096)
        kwargs["model"] = self._model
        kwargs["system"] = system
        kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = tools

        result = await self._client.messages.create(**kwargs)
        return self._normalize_response(result)

    async def chat_stream(
        self,
        messages: list[dict],
        system: str | list,
        tools: list[dict] | None = None,
        on_text_chunk: Callable[[str], None] | None = None,
        **kwargs,
    ) -> Response:
        kwargs.setdefault("max_tokens", 8096)
        kwargs["model"] = self._model
        kwargs["system"] = system
        kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                if on_text_chunk and text:
                    on_text_chunk(text)

        final = stream.get_final_message()
        return self._normalize_response(final)

    def estimate_tokens(self, text: str) -> int:
        try:
            return anthropic.count_tokens(text)
        except Exception:
            return len(text) // 4
```

Add the `Callable` import at the top:

```python
import anthropic
from collections.abc import Callable
from agentd.providers.base import BaseProvider, ContentBlock, Response
```

- [ ] **Step 2: Verify the file is valid Python**

Run: `python -c "from agentd.providers.anthropic import AnthropicProvider; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agentd/providers/anthropic.py
git commit -m "feat: implement chat_stream() in AnthropicProvider

- Uses SDK messages.stream() + text_stream async iterator
- Extracts _normalize_response() shared by chat() and chat_stream()
- Calls on_text_chunk callback for each non-empty text chunk
- Returns normalized Response via stream.get_final_message()

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-provider-streaming-refactor
---

### Task 3: ContextGuard — Add async_guard_stream_call()

**Files:**
- Modify: `agentd/context/context.py:48-49` (class declaration only), after line 321 (end of async_guard_api_call)

**Interfaces:**
- Consumes: `BaseProvider.chat_stream()` signature from Task 1
- Produces: `ContextGuard.async_guard_stream_call(system, messages, tools, on_chunk) -> Response`

- [ ] **Step 1: Add the new method to ContextGuard**

In `agentd/context/context.py`, immediately after the `async_guard_api_call()` method (after line 321, before the last blank line), add:

```python
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
```

Also add `Callable` import near the top of the file (line 3 area):

```python
import asyncio
import json
from collections.abc import Callable
from typing import Any
```

- [ ] **Step 2: Verify the file is valid Python**

Run: `python -c "from agentd.context.context import ContextGuard; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agentd/context/context.py
git commit -m "feat: add async_guard_stream_call() to ContextGuard

- Streaming path protected by: preflight, overflow (3-level), provider switch
- RATE_LIMIT/SERVER_ERROR/TIMEOUT deliberately not retried (chunks may be emitted)
- Overflow handling identical to one-shot path (truncate -> compact -> raise)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-provider-streaming-refactor
---

### Task 4: AgentRunner — Add streaming branch to run_turn()

**Files:**
- Modify: `agentd/agent/runner.py:147-155` (run_turn signature), lines 199-204 (guard call area)

**Interfaces:**
- Consumes: `ContextGuard.async_guard_stream_call()` from Task 3
- Produces: `AgentRunner.run_turn(user_input, messages, store, channel, on_text_chunk=None) -> str`

- [ ] **Step 1: Add on_text_chunk parameter and streaming branch**

In `agentd/agent/runner.py`, add `Callable` import:

```python
import logging
from collections.abc import Callable
from datetime import datetime, timezone
```

Update `run_turn()` signature (line 147-153):

```python
    async def run_turn(
        self,
        user_input: str,
        messages: list[dict],
        store: SessionStore,
        channel: str = "terminal",
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> str:
```

Inside the tool loop, replace the guard call block (lines 199-204) with a conditional that picks the guard method based on whether `on_text_chunk` is set:

```python
                # 预飞压缩：主动检查 token，超阈值先压缩
                messages = await self.guard.preflight(self._cached_system_prompt, messages)

                try:
                    if on_text_chunk is not None:
                        response = await self.guard.async_guard_stream_call(
                            system=self._cached_system_prompt,
                            messages=messages,
                            tools=self.container.tools,
                            on_chunk=on_text_chunk,
                        )
                    else:
                        response = await self.guard.async_guard_api_call(
                            system=self._cached_system_prompt,
                            messages=messages,
                            tools=self.container.tools,
                        )
                    last_response = response
```

Note: The `preflight` call above the try block is now redundant when `on_text_chunk` is set (guard stream call does its own preflight), but the preflight is cheap when under threshold and there's no harm in calling it twice. Keep it for simplicity.

Actually, to avoid redundancy, move the preflight inside the else branch only:

```python
                try:
                    if on_text_chunk is not None:
                        response = await self.guard.async_guard_stream_call(
                            system=self._cached_system_prompt,
                            messages=messages,
                            tools=self.container.tools,
                            on_chunk=on_text_chunk,
                        )
                    else:
                        # 预飞压缩：主动检查 token，超阈值先压缩
                        messages = await self.guard.preflight(self._cached_system_prompt, messages)
                        response = await self.guard.async_guard_api_call(
                            system=self._cached_system_prompt,
                            messages=messages,
                            tools=self.container.tools,
                        )
                    last_response = response
```

Remove the preflight line that was previously before the try block (line 197):

```python
                # 预飞压缩：主动检查 token，超阈值先压缩  ← remove this line
                messages = await self.guard.preflight(self._cached_system_prompt, messages)  ← remove this line
```

- [ ] **Step 2: Handle stream interruption in the exception block**

The streaming path uses the same `except ProviderError` and `except Exception` blocks. The existing `_rollback(messages)` + `return ""` logic already handles the stream-interruption case correctly:

- `on_text_chunk` chunks have already been delivered to the caller
- Rollback clears the partial messages from agent state
- Return `""` signals the caller (VoicePlatform) to send an error event to GUI

No additional code needed in the exception blocks — the existing behavior is correct.

- [ ] **Step 3: Verify the file is valid Python and imports work**

Run: `python -c "from agentd.agent.runner import AgentRunner; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Run existing tests to confirm no regression**

Run: `python test.py`
Expected: All tests pass (one-shot path unchanged)

- [ ] **Step 5: Commit**

```bash
git add agentd/agent/runner.py
git commit -m "feat: add optional on_text_chunk callback to AgentRunner.run_turn()

- When callback is None: one-shot path via guard.async_guard_api_call() (unchanged)
- When callback is set: streaming path via guard.async_guard_stream_call()
- Preflight moved inside the else (one-shot) branch — stream guard does its own
- Stream interruption returns empty string (caller detects via empty return)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-25-provider-streaming-refactor
---

### Task 5: Manual verification and final check

- [ ] **Step 1: CLI regression test**

Run: `python ultimate.py chat` and type a simple message like "hello"
Expected: Normal response, no errors, behavior identical to before

- [ ] **Step 2: Streaming quick test**

Create a temporary test script `test_stream.py`:

```python
import asyncio
from agentd.agent.runner import AgentRunner
from agentd.context.session import SessionStore
from config.configs import WORKSPACE_DIR

async def main():
    runner = AgentRunner()
    store = SessionStore(base_dir=WORKSPACE_DIR, agent_id="test")
    store.create_session("test")
    messages = []

    chunks = []
    reply = await runner.run_turn(
        user_input="say hello in one sentence",
        messages=messages,
        store=store,
        on_text_chunk=lambda t: chunks.append(t),
    )
    print(f"Chunks received: {len(chunks)}")
    print(f"Full reply: {reply[:100]}...")
    print("PASS" if chunks and reply else "FAIL")

asyncio.run(main())
```

Run: `python test_stream.py`
Expected: `PASS` with multiple chunks and a non-empty reply

- [ ] **Step 3: Clean up test script**

```bash
rm test_stream.py
```

- [ ] **Step 4: Final commit if needed**

```bash
git status
# If clean, no commit needed
```
