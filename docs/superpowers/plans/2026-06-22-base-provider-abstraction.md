---
change: base-provider-abstraction
design-doc: docs/superpowers/specs/2026-06-22-base-provider-abstraction-design.md
base-ref: db343df2106d73edfe23761fd94a32287696a807
---

# BaseProvider Abstraction 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 抽象 `BaseProvider` 接口，解耦 LLM API 层，支持多种 API 格式

**Architecture:** 新建 `agentd/providers/` 模块（`BaseProvider` ABC + `AnthropicProvider` 实现），ContextGuard 和 AgentRunner 通过 provider 实例调用 LLM，删除 `utils/clients.py` 及所有同步 API 方法

**Tech Stack:** Python 3, `anthropic` SDK, `asyncio`, dataclasses, ABC

## Global Constraints

- Async-only：删除所有同步方法（`guard_api_call`、`guard_api_call_stream`、`message_client`、`compact_history` 同步版）
- 接口：`async def chat(self, messages, system, tools, **kwargs) -> Response`
- 路径：`agentd/providers/`（非 `utils/providers/`）
- 新增：`estimate_tokens()` 方法（替代当前 `len(text)//4`）
- 类名：`BaseProvider`、`Response`、`ContentBlock`、`AnthropicProvider`
- v1 无流式，无 `create_stream`
- 实现完成后删除 `utils/clients.py`

---

### Task 1: Create BaseProvider ABC + normalized types

**Files:**
- Create: `agentd/providers/__init__.py`
- Create: `agentd/providers/base.py`

**Interfaces:**
- Produces: `BaseProvider` ABC, `Response`, `ContentBlock` dataclasses — used by Tasks 2-6
- Produces: `get_provider(config)` factory in `__init__.py` — used by Task 5

- [ ] **Step 1: Create `agentd/providers/base.py`**

```python
"""BaseProvider — LLM API 提供者抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ContentBlock:
    """归一化的响应内容块。"""
    type: str                       # "text" | "tool_use"
    text: str = ""                  # type="text" 时有值
    id: str = ""                    # type="tool_use" 时有值
    name: str = ""                  # type="tool_use" 时有值
    input: dict = field(default_factory=dict)  # type="tool_use" 时有值


@dataclass
class Response:
    """归一化的 LLM 响应。"""
    content: list[ContentBlock]
    stop_reason: str                # "end_turn" | "tool_use" | "max_tokens"


class BaseProvider(ABC):
    """LLM API 提供者抽象基类。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system: str | list,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Response:
        """发送消息并获取完整响应。"""
        ...

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数量。"""
        ...
```

- [ ] **Step 2: Create `agentd/providers/__init__.py`**

```python
"""Provider factory — 根据配置返回合适的 BaseProvider 实例。"""

from agentd.providers.base import BaseProvider, Response, ContentBlock


def get_provider(config: dict) -> BaseProvider:
    """根据 config 的 model 段返回对应的 provider 实例。

    当前仅支持 Anthropic 兼容协议；后续可扩展 OpenAI、Ollama 等。
    """
    from agentd.providers.anthropic import AnthropicProvider
    return AnthropicProvider(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["name"],
    )


__all__ = ["BaseProvider", "Response", "ContentBlock", "get_provider"]
```

- [ ] **Step 3: Verify the module imports correctly**

```bash
python -c "from agentd.providers.base import BaseProvider, Response, ContentBlock; print('base OK')"
python -c "from agentd.providers import get_provider; print('init OK')"
```

Expected: both print OK, no errors.

- [ ] **Step 4: Commit**

```bash
git add agentd/providers/__init__.py agentd/providers/base.py
git commit -m "feat: add BaseProvider ABC and normalized types"
```

- [ ] **Step 5: Sync tasks.md**

Mark Task 1 `[x]` in `openspec/changes/base-provider-abstraction/tasks.md`.

---

### Task 2: Implement AnthropicProvider

**Files:**
- Create: `agentd/providers/anthropic.py`
- Read: `utils/clients.py` (port logic, then delete in Task 5)

**Interfaces:**
- Consumes: `BaseProvider` ABC from Task 1
- Produces: `AnthropicProvider` — used by Task 5 (via `get_provider()`)
- Internal: wraps `anthropic.AsyncAnthropic`

- [ ] **Step 1: Create `agentd/providers/anthropic.py`**

```python
"""AnthropicProvider — Anthropic SDK 的 BaseProvider 实现。"""

import anthropic
from agentd.providers.base import BaseProvider, ContentBlock, Response


class AnthropicProvider(BaseProvider):
    """封装 anthropic.AsyncAnthropic，输出归一化 Response。"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self._model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
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

        # 归一化 SDK 响应
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

    def estimate_tokens(self, text: str) -> int:
        try:
            return anthropic.count_tokens(text)
        except Exception:
            return len(text) // 4
```

- [ ] **Step 2: Verify the module imports correctly**

```bash
python -c "from agentd.providers.anthropic import AnthropicProvider; print('anthropic OK')"
```

Expected: prints `anthropic OK`, no errors.

- [ ] **Step 3: Commit**

```bash
git add agentd/providers/anthropic.py
git commit -m "feat: implement AnthropicProvider"
```

- [ ] **Step 4: Sync tasks.md**

Mark Task 2 `[x]` in `openspec/changes/base-provider-abstraction/tasks.md`.

---

### Task 3: Update ContextGuard to use BaseProvider

**Files:**
- Modify: `agentd/context/context.py`

**Interfaces:**
- Consumes: `BaseProvider` from Task 1
- Produces: `ContextGuard.__init__(self, max_tokens, provider)` — used by Tasks 4-6

**Changes:**
1. Accept `provider` param in `__init__`
2. Replace `async_message_client()` calls with `await self._provider.chat()`
3. Delete `guard_api_call()`, `guard_api_call_stream()`, `compact_history()` (sync)
4. Rename `async_compact_history` → `compact_history` (now the only version)
5. Make `preflight()` async (it calls compact_history which is now async)
6. Update `estimate_tokens()` static method to use `provider.estimate_tokens()` where available

- [ ] **Step 1: Remove old imports, add new import**

In `agentd/context/context.py`, replace line 1-6:

OLD:
```python
import json
from typing import Any
from anthropic import Anthropic
from config.configs import CONTEXT_SAFE_LIMIT
from utils.print_tools import print_session, print_warn
from utils.clients import message_client, message_client_stream, async_message_client
import asyncio
```

NEW:
```python
import json
from typing import Any
from config.configs import CONTEXT_SAFE_LIMIT
from utils.print_tools import print_session, print_warn
```

- [ ] **Step 2: Update ContextGuard.__init__ and add provider-based estimate_tokens**

In class `ContextGuard`, replace lines 48-54:

OLD:
```python
class ContextGuard:
    """保护 agent 免受上下文窗口溢出。"""

    PREFLIGHT_RATIO = 0.8  # 80% 阈值触发预飞压缩

    def __init__(self, max_tokens: int = CONTEXT_SAFE_LIMIT):
        self.max_tokens = max_tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return len(text) // 4
```

NEW:
```python
class ContextGuard:
    """保护 agent 免受上下文窗口溢出。"""

    PREFLIGHT_RATIO = 0.8  # 80% 阈值触发预飞压缩

    def __init__(self, max_tokens: int = CONTEXT_SAFE_LIMIT, provider=None):
        self.max_tokens = max_tokens
        self._provider = provider

    def estimate_tokens(self, text: str) -> int:
        if self._provider is not None:
            return self._provider.estimate_tokens(text)
        return len(text) // 4
```

- [ ] **Step 3: Make preflight async**

Replace lines 88-105:

OLD:
```python
    def preflight(self, system: str, messages: list[dict]) -> list[dict]:
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
                return self.compact_history(messages)
            except Exception as exc:
                print_warn(f"  [preflight] compact failed: {exc}, skipping")
                return messages
        return messages
```

NEW:
```python
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
```

- [ ] **Step 4: Delete sync compact_history, rename async version**

Delete lines 118-176 (the entire sync `compact_history` method).

Replace lines 178-228 (the `async_compact_history` method, rename to `compact_history`):

OLD:
```python
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
```

NEW:
```python
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
            summary_resp = await self._provider.chat(
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
```

**NOTE:** After removing the sync `compact_history` and renaming `async_compact_history` → `compact_history`, there is now only ONE `compact_history` method (async). Update `preflight` (Step 3) to `await self.compact_history(...)`.

- [ ] **Step 5: Delete sync guard_api_call and guard_api_call_stream, update async_guard_api_call**

Delete lines 251-347 (the entire `guard_api_call` and `guard_api_call_stream` methods).

Replace lines 349-402 (update `async_guard_api_call` to use provider):

OLD:
```python
    async def async_guard_api_call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_retries: int = 1,
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
```

NEW:
```python
    async def async_guard_api_call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_retries: int = 1,
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
                result = await self._provider.chat(
                    messages=current_messages,
                    system=system,
                    tools=tools,
                    max_tokens=8096,
                )

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
                    current_messages = await self.compact_history(current_messages)

        raise RuntimeError("async_guard_api_call: exhausted retries")
```

- [ ] **Step 6: Verify the context module imports and has no syntax errors**

```bash
python -c "from agentd.context.context import ContextGuard, _serialize_messages_for_summary; print('context OK')"
```

Expected: prints `context OK`, no import errors.

- [ ] **Step 7: Commit**

```bash
git add agentd/context/context.py
git commit -m "refactor: ContextGuard uses BaseProvider, remove sync methods"
```

- [ ] **Step 8: Sync tasks.md**

Mark Task 3 `[x]` in `openspec/changes/base-provider-abstraction/tasks.md`.

---

### Task 4: Update AgentRunner serialization

**Files:**
- Modify: `agentd/agent/runner.py`

**Interfaces:**
- Consumes: `Response`, `ContentBlock` from Task 1; updated `ContextGuard` from Task 3
- Produces: `AgentRunner._serialize()`, `AgentRunner._extract_text()` work with dataclass types

- [ ] **Step 1: Update _serialize and _extract_text to use ContentBlock attributes**

Replace lines 51-69:

OLD:
```python
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
```

NEW:
```python
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
```

- [ ] **Step 2: Update run_turn — preflight call, message appending, tool_use iteration**

There are three changes in `run_turn()`:

**Change A — preflight (line 124):**

OLD:
```python
            messages = self.guard.preflight(self._cached_system_prompt, messages)
```

NEW:
```python
            messages = await self.guard.preflight(self._cached_system_prompt, messages)
```

**Change B — append assistant response to messages (line 138):**

OLD:
```python
            messages.append({"role": "assistant", "content": response.content})
```

NEW:
```python
            messages.append({"role": "assistant", "content": self._serialize(response)})
```

Wait — this changes the stored format. Previously `response.content` was raw SDK ContentBlock objects. Now we store the serialized dict list. This affects:
- `_serialize_messages_for_summary()` in context.py — which already handles dicts via `isinstance(block, dict)` path
- `estimate_messages_tokens()` — which already handles dicts

So this change is correct and actually simplifies things. The dict form is already supported everywhere.

**Change C — tool_use iteration (lines 146-155):**

OLD:
```python
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = self.process_tool_call(block.name, block.input)
```

NEW (unchanged — `ContentBlock.type`, `.name`, `.input` work identically):

The field accesses `block.type`, `block.name`, `block.input` work identically on `ContentBlock` dataclass as they did on SDK `ToolUseBlock`. No change needed for this part.

- [ ] **Step 3: Actually apply all three changes**

Change A — line 123-124:
```python
            # 预飞压缩：主动检查 token，超阈值先压缩
            messages = await self.guard.preflight(self._cached_system_prompt, messages)
```

Change B — line 138:
```python
            messages.append({"role": "assistant", "content": self._serialize(response)})
```

- [ ] **Step 4: Verify the runner module compiles**

```bash
python -c "from agentd.agent.runner import AgentRunner; print('runner OK')"
```

Expected: prints `runner OK`, no errors.

NOTE: This will fail if `Container` hasn't been updated to inject `provider` into `ContextGuard`. This is expected — the full chain requires Task 5.

- [ ] **Step 5: Commit**

```bash
git add agentd/agent/runner.py
git commit -m "refactor: AgentRunner serialization uses normalized types"
```

- [ ] **Step 6: Sync tasks.md**

Mark Task 4 `[x]` in `openspec/changes/base-provider-abstraction/tasks.md`.

---

### Task 5: Wire provider selection from config

**Files:**
- Modify: `agentd/bootstrap/container.py`
- Modify: `config/configs.py`
- Delete: `utils/clients.py`

**Interfaces:**
- Consumes: `get_provider()` from Task 1, `AnthropicProvider` from Task 2
- Produces: `Container` creates provider and passes to `ContextGuard`

- [ ] **Step 1: Add convenience import to config/configs.py**

In `config/configs.py`, add after line 24 (`MODEL = ...`):

```python
def get_model_provider():
    """返回基于 config.json 的 BaseProvider 实例。"""
    from agentd.providers import get_provider
    return get_provider(MODEL)
```

- [ ] **Step 2: Update container.py to create provider and inject into ContextGuard**

Replace lines 1-39 entirely:

OLD:
```python
from config.configs import WORKSPACE_DIR
from agentd.bootstrap.loader import BootstrapLoader
from agentd.skill.skill import SkillsManager
from agentd.memory.memory import MemoryStore
from agentd.context.session import SessionStore
from agentd.context.context import ContextGuard
from agentd.tools.tool_handlers import get_tools, get_tool_handlers

class Container:
    def __init__(self):
        self.tools = []
        self.tools_handlers = {}
        self.services = {}

        self.initialize()

    def register(self, name, instance):
        self.services[name] = instance

    def get(self, name):
        return self.services[name]

    def initialize(self):
        # 这里可以添加一些全局初始化的逻辑，比如加载工具、设置环境变量等
        loader = BootstrapLoader(WORKSPACE_DIR)
        bootstrap_data = loader.load_all(mode="full")
        skills_mgr = SkillsManager(WORKSPACE_DIR)
        skills_mgr.discover()
        memory_store = MemoryStore(WORKSPACE_DIR)
        guard = ContextGuard()

        self.register("bootstrap_data", bootstrap_data)
        self.register("skills_mgr", skills_mgr)
        self.register("memory_store", memory_store)
        self.register("guard", guard)

        self.tools = get_tools()
        self.tools_handlers = get_tool_handlers()

# ✅ 全局唯一实例（但不是全局变量乱飞）
container = Container()
```

NEW:
```python
from config.configs import WORKSPACE_DIR, get_model_provider
from agentd.bootstrap.loader import BootstrapLoader
from agentd.skill.skill import SkillsManager
from agentd.memory.memory import MemoryStore
from agentd.context.session import SessionStore
from agentd.context.context import ContextGuard
from agentd.tools.tool_handlers import get_tools, get_tool_handlers

class Container:
    def __init__(self):
        self.tools = []
        self.tools_handlers = {}
        self.services = {}

        self.initialize()

    def register(self, name, instance):
        self.services[name] = instance

    def get(self, name):
        return self.services[name]

    def initialize(self):
        loader = BootstrapLoader(WORKSPACE_DIR)
        bootstrap_data = loader.load_all(mode="full")
        skills_mgr = SkillsManager(WORKSPACE_DIR)
        skills_mgr.discover()
        memory_store = MemoryStore(WORKSPACE_DIR)

        # Provider — 由 config.json 驱动
        provider = get_model_provider()
        guard = ContextGuard(provider=provider)

        self.register("bootstrap_data", bootstrap_data)
        self.register("skills_mgr", skills_mgr)
        self.register("memory_store", memory_store)
        self.register("guard", guard)
        self.register("provider", provider)

        self.tools = get_tools()
        self.tools_handlers = get_tool_handlers()

# ✅ 全局唯一实例（但不是全局变量乱飞）
container = Container()
```

- [ ] **Step 3: Delete utils/clients.py**

```bash
git rm utils/clients.py
```

- [ ] **Step 4: Verify full module chain**

```bash
python -c "from agentd.bootstrap import container; print('container OK')"
python -c "from config.configs import get_model_provider; p = get_model_provider(); print(type(p).__name__)"
```

Expected: prints `container OK` and `AnthropicProvider`.

- [ ] **Step 5: Commit**

```bash
git add config/configs.py agentd/bootstrap/container.py utils/clients.py
git commit -m "refactor: wire provider from config, delete utils/clients.py"
```

- [ ] **Step 6: Sync tasks.md**

Mark Task 5 `[x]` in `openspec/changes/base-provider-abstraction/tasks.md`.

---

### Task 6: Update CLI/Gateway entry points

**Files:**
- Modify: `cli/cli.py`
- Modify: `gateway/gateway.py`

**Interfaces:**
- Consumes: Updated `AgentRunner` from Task 4, updated `ContextGuard` from Task 3
- Each entry point creates `AgentRunner()` which internally gets provider via container

- [ ] **Step 1: Update cli/cli.py — /compact command to use async**

The `/compact` handler (line 167-175) calls `self.runner.guard.compact_history(self.messages)` which is now async. Convert to use `asyncio.run()`:

Replace lines 167-175:

OLD:
```python
        elif cmd == "/compact":
            if len(self.messages) <= 4:
                print_info("  Too few messages to compact (need > 4).")
                return True
            print_session("  Compacting history...")
            new_messages = self.runner.guard.compact_history(self.messages)
            print_session(f"  {len(self.messages)} -> {len(new_messages)} messages")
            self.messages = new_messages
            return True
```

NEW:
```python
        elif cmd == "/compact":
            if len(self.messages) <= 4:
                print_info("  Too few messages to compact (need > 4).")
                return True
            print_session("  Compacting history...")

            async def _compact():
                return await self.runner.guard.compact_history(self.messages)
            new_messages = asyncio.run(_compact())

            print_session(f"  {len(self.messages)} -> {len(new_messages)} messages")
            self.messages = new_messages
            return True
```

- [ ] **Step 2: Verify cli.py imports correctly**

```bash
python -c "from cli.cli import Cli; print('cli OK')"
```

Expected: prints `cli OK`, no errors.

- [ ] **Step 3: Verify gateway.py imports correctly**

gateway.py does not directly import from `utils/clients.py` or call any sync API methods — it only uses `AgentRunner`. No code changes needed for gateway.py.

```bash
python -c "from gateway.gateway import Gateway; print('gateway OK')"
```

Expected: prints `gateway OK`, no errors.

- [ ] **Step 4: Commit**

```bash
git add cli/cli.py
git commit -m "fix: /compact uses async compact_history"
```

- [ ] **Step 5: Sync tasks.md**

Mark Task 6 `[x]` in `openspec/changes/base-provider-abstraction/tasks.md`.

---

### Task 7: Verify end-to-end

**Files:**
- No new files. Run verification checks.

- [ ] **Step 1: Run Python compilation check**

```bash
python -m py_compile agentd/providers/base.py agentd/providers/anthropic.py agentd/providers/__init__.py agentd/context/context.py agentd/agent/runner.py agentd/bootstrap/container.py cli/cli.py gateway/gateway.py
```

Expected: no output (all files compile cleanly).

- [ ] **Step 2: Verify full import chain**

```bash
python -c "
from agentd.providers import BaseProvider, Response, ContentBlock, get_provider
from agentd.providers.anthropic import AnthropicProvider
from agentd.context.context import ContextGuard
from agentd.agent.runner import AgentRunner
from config.configs import MODEL, get_model_provider
print('All imports OK')
"
```

Expected: prints `All imports OK`.

- [ ] **Step 3: Confirm utils/clients.py is deleted**

```bash
test -f utils/clients.py && echo "STILL EXISTS" || echo "DELETED OK"
```

Expected: `DELETED OK`.

- [ ] **Step 4: Confirm no remaining references to old clients**

```bash
grep -r "message_client\|async_message_client\|stream_client\|from utils.clients" --include="*.py" . || echo "NO OLD REFS FOUND"
```

Expected: `NO OLD REFS FOUND` (or only in git history).

- [ ] **Step 5: Sync tasks.md — mark all tasks complete**

Mark Task 7 `[x]` in `openspec/changes/base-provider-abstraction/tasks.md`.

Confirm all 7 tasks are `[x]`:

```bash
grep -c '\[x\]' openspec/changes/base-provider-abstraction/tasks.md
```

Expected: `7`.

- [ ] **Step 6: Commit**

```bash
git add openspec/changes/base-provider-abstraction/tasks.md
git commit -m "chore: mark all tasks complete, verify end-to-end"
```

---

## 完成验证

全部 7 个任务提交后：

```bash
# 确认文件改动
git diff --stat db343df2106d73edfe23761fd94a32287696a807...HEAD

# 预期改动:
#  新建: agentd/providers/__init__.py
#  新建: agentd/providers/base.py
#  新建: agentd/providers/anthropic.py
#  修改: agentd/context/context.py
#  修改: agentd/agent/runner.py
#  修改: agentd/bootstrap/container.py
#  修改: config/configs.py
#  修改: cli/cli.py
#  删除: utils/clients.py

# 确认 tasks.md 全部勾选
grep -c '\[x\]' openspec/changes/base-provider-abstraction/tasks.md
# 预期: 7
```
