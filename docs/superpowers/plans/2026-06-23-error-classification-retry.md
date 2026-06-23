---
change: error-classification-retry
design-doc: docs/superpowers/specs/2026-06-23-error-classification-retry-design.md
base-ref: 83549a481757f03cd058edd9a7b73491ee1b263b
archived-with: 2026-06-23-error-classification-retry
---

# Error Classification + Differentiated Retry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace bare `except Exception` with typed error classification and differentiated retry strategies for API calls.

**Architecture:** ErrorMapper (SDK exc → typed ProviderError) → ProviderRouter (primary/backup) → ContextGuard (strategy dispatch) → AgentRunner (structured propagation). Each layer is independently testable.

**Tech Stack:** Python 3.12+ stdlib (`enum`, `asyncio`), Anthropic SDK exception types, `unittest.mock`

## Global Constraints

- Pure Python standard library, zero external dependencies
- Router reset to primary provider at start of each `run_turn()`
- User-visible prompt before each retry
- `UNKNOWN` errors never retry
- All 14 existing tests must keep passing
- Each task commits independently with descriptive message

archived-with: 2026-06-23-error-classification-retry
---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `agentd/providers/base.py` | Modify | Add `ErrorType` enum + `ProviderError` exception |
| `agentd/providers/error_mapper.py` | **Create** | `classify()` function: SDK exc → `ProviderError` |
| `agentd/providers/router.py` | **Create** | `ProviderRouter` class: primary/backup switching |
| `agentd/providers/__init__.py` | Modify | Add `get_all_providers()` factory |
| `agentd/context/context.py` | Modify | Rewrite `async_guard_api_call()` retry logic |
| `agentd/bootstrap/container.py` | Modify | Wire `ProviderRouter` + `ErrorMapper` |
| `agentd/agent/runner.py` | Modify | Structured `ProviderError` propagation |
| `tests/test_error_mapper.py` | **Create** | Unit tests for ErrorMapper |
| `tests/test_provider_router.py` | **Create** | Unit tests for ProviderRouter |
| `tests/test_guard_retry.py` | **Create** | Mock-based tests for ContextGuard retry |

archived-with: 2026-06-23-error-classification-retry
---

### Task 1: ErrorType 枚举 + ProviderError 异常

**Files:**
- Modify: `agentd/providers/base.py:1-41`
- Test: `tests/test_error_mapper.py` (later tasks will add more tests)

**Interfaces:**
- Produces: `ErrorType(Enum)` — `CONTEXT_OVERFLOW`, `RATE_LIMIT`, `AUTH_FAILURE`, `SERVER_ERROR`, `TIMEOUT`, `MODEL_UNAVAILABLE`, `UNKNOWN`
- Produces: `ProviderError(Exception)` — `error_type: ErrorType`, `message: str`, `status_code: int`, `original: Exception | None`

- [ ] **Step 1: Add ErrorType enum and ProviderError to base.py**

Add at the end of `agentd/providers/base.py` (after the existing `BaseProvider` class):

```python
from enum import Enum


class ErrorType(Enum):
    """LLM API 错误的类型化分类。"""
    CONTEXT_OVERFLOW  = "context_overflow"
    RATE_LIMIT        = "rate_limit"
    AUTH_FAILURE      = "auth_failure"
    SERVER_ERROR      = "server_error"
    TIMEOUT           = "timeout"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNKNOWN           = "unknown"


class ProviderError(Exception):
    """类型化的 provider 错误，携带分类元数据。"""

    def __init__(self, error_type: ErrorType, message: str,
                 status_code: int = 0,
                 original: Exception | None = None):
        self.error_type = error_type
        self.status_code = status_code
        self.original = original
        super().__init__(message)
```

- [ ] **Step 2: Verify ErrorType values exist**

```bash
python -c "from agentd.providers.base import ErrorType, ProviderError; e = ProviderError(ErrorType.RATE_LIMIT, 'test', 429); assert e.error_type.value == 'rate_limit'; assert e.status_code == 429; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run existing tests to confirm no regression**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/ -v
```

Expected: 14 passed (or all existing tests pass)

- [ ] **Step 4: Commit**

```bash
git add agentd/providers/base.py
git commit -m "feat: add ErrorType enum and ProviderError to base provider module

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-error-classification-retry
---

### Task 2: ErrorMapper — SDK 异常映射

**Files:**
- Create: `agentd/providers/error_mapper.py`
- Create: `tests/test_error_mapper.py`

**Interfaces:**
- Consumes: `ErrorType`, `ProviderError` from `agentd/providers.base`
- Produces: `classify(exc: Exception) -> ProviderError` — stateless function

- [ ] **Step 1: Write the test file**

Create `tests/test_error_mapper.py`:

```python
"""Tests for ErrorMapper — SDK exception classification."""
import pytest
from agentd.providers.base import ErrorType, ProviderError
from agentd.providers.error_mapper import classify


# ── Helpers: mock SDK-like exceptions ──────────────────────────

class MockRateLimitError(Exception):
    def __init__(self, msg="rate limit exceeded", status_code=429):
        self.status_code = status_code
        super().__init__(msg)


class MockAuthError(Exception):
    def __init__(self, msg="invalid api key", status_code=401):
        self.status_code = status_code
        super().__init__(msg)


class MockServerError(Exception):
    def __init__(self, msg="internal error", status_code=500):
        self.status_code = status_code
        super().__init__(msg)


class MockTimeoutError(Exception):
    pass


class MockNotFoundError(Exception):
    def __init__(self, msg="model not found", status_code=404):
        self.status_code = status_code
        super().__init__(msg)


class MockBadRequestError(Exception):
    def __init__(self, msg="context_length_exceeded: too many tokens", status_code=400):
        self.status_code = status_code
        super().__init__(msg)


# ── Tests ──────────────────────────────────────────────────────


class TestErrorMapperPrecision:
    """Exact type matching via isinstance checks."""

    def test_rate_limit_via_type(self):
        err = classify(MockRateLimitError())
        assert err.error_type == ErrorType.RATE_LIMIT

    def test_auth_failure_via_type(self):
        err = classify(MockAuthError())
        assert err.error_type == ErrorType.AUTH_FAILURE

    def test_server_error_via_type(self):
        err = classify(MockServerError())
        assert err.error_type == ErrorType.SERVER_ERROR

    def test_timeout_via_type(self):
        err = classify(MockTimeoutError())
        assert err.error_type == ErrorType.TIMEOUT

    def test_model_unavailable_via_type(self):
        err = classify(MockNotFoundError())
        assert err.error_type == ErrorType.MODEL_UNAVAILABLE

    def test_context_overflow_via_type(self):
        err = classify(MockBadRequestError())
        assert err.error_type == ErrorType.CONTEXT_OVERFLOW


class TestErrorMapperStatusCodeFallback:
    """Status code fallback for non-standard exception types."""

    def test_rate_limit_via_status(self):
        class Generic429(Exception):
            status_code = 429
        err = classify(Generic429("too many requests"))
        assert err.error_type == ErrorType.RATE_LIMIT

    def test_auth_via_status(self):
        class Generic401(Exception):
            status_code = 401
        err = classify(Generic401("unauthorized"))
        assert err.error_type == ErrorType.AUTH_FAILURE

    def test_server_error_via_status(self):
        class Generic503(Exception):
            status_code = 503
        err = classify(Generic503("service unavailable"))
        assert err.error_type == ErrorType.SERVER_ERROR


class TestErrorMapperKeywordFallback:
    """Keyword matching for providers with non-standard error formats."""

    def test_rate_limit_keyword(self):
        err = classify(Exception("rate limit exceeded, try again"))
        assert err.error_type == ErrorType.RATE_LIMIT

    def test_auth_keyword(self):
        err = classify(Exception("invalid api key provided"))
        assert err.error_type == ErrorType.AUTH_FAILURE

    def test_timeout_keyword(self):
        err = classify(Exception("request timeout"))
        assert err.error_type == ErrorType.TIMEOUT

    def test_context_keyword(self):
        err = classify(Exception("context token limit exceeded"))
        assert err.error_type == ErrorType.CONTEXT_OVERFLOW

    def test_model_not_found_keyword(self):
        err = classify(Exception("model deepseek-v5 not found"))
        assert err.error_type == ErrorType.MODEL_UNAVAILABLE


class TestErrorMapperUnknown:
    """Unrecognizable errors map to UNKNOWN."""

    def test_unknown_random_exception(self):
        err = classify(ValueError("something weird"))
        assert err.error_type == ErrorType.UNKNOWN

    def test_unknown_empty(self):
        err = classify(Exception())
        assert err.error_type == ErrorType.UNKNOWN


class TestProviderErrorMetadata:
    """ProviderError carries full context."""

    def test_original_exception_preserved(self):
        orig = MockRateLimitError("too fast")
        err = classify(orig)
        assert err.original is orig

    def test_status_code_preserved(self):
        err = classify(MockRateLimitError(status_code=429))
        assert err.status_code == 429

    def test_message_preserved(self):
        err = classify(MockAuthError("bad key"))
        assert "bad key" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_error_mapper.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agentd.providers.error_mapper'`

- [ ] **Step 3: Implement ErrorMapper**

Create `agentd/providers/error_mapper.py`:

```python
"""ErrorMapper — SDK 异常 → ProviderError 类型化映射。

三级匹配策略（按优先级）：
  1. 精确类型匹配 — isinstance 检查已知 SDK 异常类型
  2. status_code 回退 — 当异常对象有 status_code 属性时
  3. 消息关键词兜底 — 检查错误消息字符串中的关键词
"""
from agentd.providers.base import ErrorType, ProviderError


# ── 类型匹配表 ──────────────────────────────────────────────────
# 格式: (异常类名, ErrorType) — 按优先级排列
_TYPE_MAP: list[tuple[str, ErrorType]] = [
    ("RateLimitError",      ErrorType.RATE_LIMIT),
    ("AuthenticationError", ErrorType.AUTH_FAILURE),
    ("PermissionDeniedError", ErrorType.AUTH_FAILURE),
    ("InternalServerError", ErrorType.SERVER_ERROR),
    ("APITimeoutError",     ErrorType.TIMEOUT),
    ("NotFoundError",       ErrorType.MODEL_UNAVAILABLE),
]

# ── 消息关键词兜底表 ───────────────────────────────────────────
_KEYWORD_MAP: list[tuple[list[str], ErrorType]] = [
    (["rate", "limit"],                  ErrorType.RATE_LIMIT),
    (["auth", "key"],                    ErrorType.AUTH_FAILURE),
    (["unauthorized", "forbidden"],      ErrorType.AUTH_FAILURE),
    (["timeout", "timed out"],           ErrorType.TIMEOUT),
    (["context", "token", "length"],     ErrorType.CONTEXT_OVERFLOW),
    (["model", "not found", "unavailable"], ErrorType.MODEL_UNAVAILABLE),
    (["internal", "server error"],       ErrorType.SERVER_ERROR),
    (["service unavailable", "overloaded"], ErrorType.SERVER_ERROR),
]


def classify(exc: Exception) -> ProviderError:
    """将 SDK 异常映射为类型化 ProviderError。

    三级匹配：
      1. 精确类型匹配（类名包含已知 SDK 异常名）
      2. status_code 匹配（针对有 status_code 属性的异常）
      3. 消息关键词兜底（针对非标准 provider）
    全部不匹配则返回 UNKNOWN。
    """
    msg = str(exc)
    status_code = getattr(exc, "status_code", 0) or 0
    exc_type_name = type(exc).__name__

    # Level 1: 精确类型匹配
    for sdk_name, error_type in _TYPE_MAP:
        if sdk_name in exc_type_name or sdk_name.lower() in exc_type_name.lower():
            return ProviderError(error_type, msg, status_code=status_code, original=exc)

    # Context overflow 特殊处理: BadRequestError + context_length
    if status_code == 400 and ("context" in msg.lower() or "token" in msg.lower()):
        return ProviderError(ErrorType.CONTEXT_OVERFLOW, msg, status_code=status_code, original=exc)
    if status_code == 400 and ("BadRequest" in exc_type_name or "bad request" in exc_type_name.lower()):
        # 400 could be context overflow or bad request — check message
        if "context" in msg.lower() or "token" in msg.lower() or "length" in msg.lower():
            return ProviderError(ErrorType.CONTEXT_OVERFLOW, msg, status_code=status_code, original=exc)

    # Level 2: status_code 回退
    if status_code == 429:
        return ProviderError(ErrorType.RATE_LIMIT, msg, status_code=status_code, original=exc)
    if status_code in (401, 403):
        return ProviderError(ErrorType.AUTH_FAILURE, msg, status_code=status_code, original=exc)
    if status_code >= 500:
        return ProviderError(ErrorType.SERVER_ERROR, msg, status_code=status_code, original=exc)
    if status_code == 404:
        return ProviderError(ErrorType.MODEL_UNAVAILABLE, msg, status_code=status_code, original=exc)
    if status_code == 408:
        return ProviderError(ErrorType.TIMEOUT, msg, status_code=status_code, original=exc)

    # Level 3: 消息关键词兜底
    msg_lower = msg.lower()
    for keywords, error_type in _KEYWORD_MAP:
        if all(kw in msg_lower for kw in keywords):
            return ProviderError(error_type, msg, status_code=status_code, original=exc)

    # 无法识别
    return ProviderError(ErrorType.UNKNOWN, msg, status_code=status_code, original=exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_error_mapper.py -v
```

Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add agentd/providers/error_mapper.py tests/test_error_mapper.py
git commit -m "feat: add ErrorMapper for typed SDK exception classification

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-error-classification-retry
---

### Task 3: ProviderRouter — 主备切换

**Files:**
- Create: `agentd/providers/router.py`
- Create: `tests/test_provider_router.py`

**Interfaces:**
- Consumes: `BaseProvider` from `agentd/providers.base`
- Produces: `ProviderRouter` — `current: BaseProvider`, `switch() -> bool`, `reset() -> None`

- [ ] **Step 1: Write the test file**

Create `tests/test_provider_router.py`:

```python
"""Tests for ProviderRouter — primary/backup switching."""
import pytest
from agentd.providers.base import BaseProvider, Response
from agentd.providers.router import ProviderRouter


class FakeProvider(BaseProvider):
    """Minimal fake provider for router tests."""
    def __init__(self, name):
        self.name = name

    async def chat(self, messages, system, tools=None, **kwargs):
        return Response(content=[], stop_reason="end_turn")

    def estimate_tokens(self, text):
        return len(text) // 4


class TestProviderRouterInit:
    """Construction and current property."""

    def test_single_provider(self):
        p = FakeProvider("main")
        r = ProviderRouter([p])
        assert r.current is p

    def test_multiple_providers_first_is_current(self):
        p1 = FakeProvider("main")
        p2 = FakeProvider("backup")
        r = ProviderRouter([p1, p2])
        assert r.current is p1

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="至少需要"):
            ProviderRouter([])


class TestProviderRouterSwitch:
    """Switch to backup providers."""

    def test_switch_to_backup(self):
        p1 = FakeProvider("main")
        p2 = FakeProvider("backup")
        r = ProviderRouter([p1, p2])
        assert r.switch() is True
        assert r.current is p2

    def test_switch_chain(self):
        p1 = FakeProvider("p1")
        p2 = FakeProvider("p2")
        p3 = FakeProvider("p3")
        r = ProviderRouter([p1, p2, p3])
        assert r.switch() is True
        assert r.current is p2
        assert r.switch() is True
        assert r.current is p3

    def test_switch_at_last_returns_false(self):
        p1 = FakeProvider("only")
        r = ProviderRouter([p1])
        assert r.switch() is False
        assert r.current is p1  # unchanged

    def test_switch_exhausted_returns_false(self):
        p1 = FakeProvider("p1")
        p2 = FakeProvider("p2")
        r = ProviderRouter([p1, p2])
        r.switch()  # to p2
        assert r.switch() is False  # no more
        assert r.current is p2  # stays on last


class TestProviderRouterReset:
    """Reset back to primary."""

    def test_reset_to_primary(self):
        p1 = FakeProvider("main")
        p2 = FakeProvider("backup")
        r = ProviderRouter([p1, p2])
        r.switch()
        assert r.current is p2
        r.reset()
        assert r.current is p1

    def test_double_reset(self):
        p1 = FakeProvider("main")
        r = ProviderRouter([p1])
        r.reset()
        r.reset()
        assert r.current is p1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_provider_router.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ProviderRouter**

Create `agentd/providers/router.py`:

```python
"""ProviderRouter — 管理多 provider 主备切换。

主备模式: providers[0] 为主，后续为备。
switch() 依次切换到下一个 provider，reset() 回到主。
"""
from agentd.providers.base import BaseProvider


class ProviderRouter:
    """按主备顺序管理多个 BaseProvider 实例。"""

    def __init__(self, providers: list[BaseProvider]):
        if not providers:
            raise ValueError("至少需要一个 provider")
        self._providers = providers
        self._idx = 0

    @property
    def current(self) -> BaseProvider:
        """返回当前活跃的 provider。"""
        return self._providers[self._idx]

    def switch(self) -> bool:
        """切换到下一个备选 provider。

        返回 True 表示切换成功，False 表示已无可切换 provider。
        """
        if self._idx + 1 < len(self._providers):
            self._idx += 1
            return True
        return False

    def reset(self) -> None:
        """回到主 provider（每 turn 开始时调用）。"""
        self._idx = 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_provider_router.py -v
```

Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add agentd/providers/router.py tests/test_provider_router.py
git commit -m "feat: add ProviderRouter for primary/backup provider switching

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-error-classification-retry
---

### Task 4: Provider factory — 支持多实例

**Files:**
- Modify: `agentd/providers/__init__.py:1-42`
- Modify: `agentd/bootstrap/container.py:1-51`

**Interfaces:**
- Consumes: `Config` from `config.configs`, `AnthropicProvider`, `ProviderRouter` from `agentd.providers.router`
- Produces: `get_all_providers(config) -> list[AnthropicProvider]`
- Modifies: Container `initialize()` to create `ProviderRouter` and register it

- [ ] **Step 1: Add get_all_providers to __init__.py**

Modify `agentd/providers/__init__.py` — add `get_all_providers()` function after the existing `get_provider()`:

```python
def get_all_providers(config) -> list:
    """返回 config 中所有 provider 的实例列表。

    第一个是主 provider，后续是备选。
    用于构造 ProviderRouter。
    """
    from agentd.providers.anthropic import AnthropicProvider

    instances = []
    for provider_cfg in config.model.providers:
        if not provider_cfg.api_key:
            continue  # 跳过未配置 key 的 provider
        instances.append(AnthropicProvider(
            api_key=provider_cfg.api_key,
            base_url=provider_cfg.base_url,
            model=provider_cfg.model,
        ))

    if not instances:
        raise ValueError(
            "No providers with valid API keys configured. "
            "Check config.yaml model.providers and environment variables."
        )
    return instances
```

Update `__all__` at the bottom of the file:

```python
__all__ = ["BaseProvider", "Response", "ContentBlock", "ErrorType", "ProviderError",
           "get_provider", "get_all_providers"]
```

- [ ] **Step 2: Update Container to use ProviderRouter**

Modify `agentd/bootstrap/container.py` — replace the provider setup:

Old (lines 36-38):
```python
        # Provider — 由 config.yaml 驱动
        provider = get_model_provider()
        guard = ContextGuard(provider=provider)
```

New:
```python
        # Provider — 由 config.yaml 驱动，主备模式
        from agentd.providers import get_all_providers
        from agentd.providers.router import ProviderRouter
        all_providers = get_all_providers(get_config())
        provider_router = ProviderRouter(all_providers)
        guard = ContextGuard(provider_router=provider_router)
```

Update registrations (lines 40-45):
```python
        self.register("bootstrap_data", bootstrap_data)
        self.register("skills_mgr", skills_mgr)
        self.register("memory_store", memory_store)
        self.register("session_db", session_db)
        self.register("guard", guard)
        self.register("provider_router", provider_router)
```

Add the import for `get_config` at the top of the file (line 1):
```python
from config.configs import WORKSPACE_DIR, get_model_provider, get_config
```

- [ ] **Step 3: Verify build passes**

```bash
cd c:/self/work/todo/ultimate_try && python -c "from agentd.bootstrap.container import Container; c = Container(); print('ProviderRouter registered:', c.get('provider_router').current._model)"
```

Expected: prints current model and succeeds

- [ ] **Step 4: Run all existing tests**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/ -v
```

Expected: all existing tests pass (22 = 14 original + 17 error_mapper + 8 router — but the new test files also run)

- [ ] **Step 5: Commit**

```bash
git add agentd/providers/__init__.py agentd/bootstrap/container.py
git commit -m "feat: add get_all_providers factory and wire ProviderRouter into container

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-error-classification-retry
---

### Task 5: ContextGuard 策略分发重写

**Files:**
- Modify: `agentd/context/context.py:191-240` (rewrite `async_guard_api_call`)
- Create: `tests/test_guard_retry.py`

**Interfaces:**
- Consumes: `ProviderRouter` (instead of single `provider`), `ErrorType`, `ProviderError`, `classify` from `error_mapper`
- Modifies: `async_guard_api_call()` — new signature accepting `provider_router`, dispatch by `ErrorType`

- [ ] **Step 1: Write the test file**

Create `tests/test_guard_retry.py`:

```python
"""Tests for ContextGuard retry strategy dispatch."""
import asyncio
import pytest
from unittest.mock import AsyncMock, Mock
from agentd.providers.base import (
    ErrorType, ProviderError, Response, ContentBlock, BaseProvider
)
from agentd.context.context import ContextGuard
from agentd.providers.router import ProviderRouter


def make_response(text="ok"):
    return Response(
        content=[ContentBlock(type="text", text=text)],
        stop_reason="end_turn",
    )


def make_error(error_type, msg="test error", status_code=0):
    return ProviderError(error_type, msg, status_code=status_code)


class FakeProvider(BaseProvider):
    """Provider that throws or returns based on injected behavior."""
    def __init__(self, name="fake"):
        self.name = name
        self.chat = AsyncMock()

    def estimate_tokens(self, text):
        return len(text) // 4


class TestGuardRetry:
    """Test that each ErrorType triggers the correct retry behavior."""

    @pytest.mark.asyncio
    async def test_unknown_error_not_retried(self):
        """UNKNOWN errors should be raised immediately, no retry."""
        p = FakeProvider()
        p.chat.side_effect = make_error(ErrorType.UNKNOWN, "weird error")
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError) as exc_info:
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert exc_info.value.error_type == ErrorType.UNKNOWN
        assert p.chat.call_count == 1  # no retry

    @pytest.mark.asyncio
    async def test_rate_limit_exponential_backoff(self):
        """RATE_LIMIT should retry with exponential backoff."""
        p = FakeProvider()
        p.chat.side_effect = [
            make_error(ErrorType.RATE_LIMIT, "too fast", 429),
            make_error(ErrorType.RATE_LIMIT, "still fast", 429),
            make_response("finally"),
        ]
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert p.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted(self):
        """After 3 RATE_LIMIT retries, should raise."""
        p = FakeProvider()
        p.chat.side_effect = [
            make_error(ErrorType.RATE_LIMIT, "too fast", 429),
            make_error(ErrorType.RATE_LIMIT, "too fast", 429),
            make_error(ErrorType.RATE_LIMIT, "too fast", 429),
        ]
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError):
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert p.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_auth_failure_switches_provider(self):
        """AUTH_FAILURE should switch to backup provider."""
        p1 = FakeProvider("main")
        p1.chat.side_effect = make_error(ErrorType.AUTH_FAILURE, "bad key", 401)
        p2 = FakeProvider("backup")
        p2.chat.return_value = make_response("backup works")
        router = ProviderRouter([p1, p2])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert p2.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_auth_failure_no_backup_raises(self):
        """AUTH_FAILURE with no backup should raise."""
        p = FakeProvider()
        p.chat.side_effect = make_error(ErrorType.AUTH_FAILURE, "bad key", 401)
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError) as exc_info:
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert exc_info.value.error_type == ErrorType.AUTH_FAILURE
        assert p.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_server_error_linear_retry(self):
        """SERVER_ERROR should retry with linear backoff."""
        p = FakeProvider()
        p.chat.side_effect = [
            make_error(ErrorType.SERVER_ERROR, "500", 500),
            make_response("ok"),
        ]
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert p.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_increases_timeout(self):
        """TIMEOUT should retry with increased timeout."""
        p = FakeProvider()
        call_timeouts = []

        async def fake_chat(messages, system, tools=None, timeout=None, **kwargs):
            call_timeouts.append(timeout)
            if len(call_timeouts) < 2:
                raise make_error(ErrorType.TIMEOUT, "timeout")
            return make_response("ok")

        p.chat.side_effect = fake_chat
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert call_timeouts[0] == 30   # default
        assert call_timeouts[1] == 60   # increased

    @pytest.mark.asyncio
    async def test_model_unavailable_switches_provider(self):
        """MODEL_UNAVAILABLE should switch to backup provider."""
        p1 = FakeProvider("main")
        p1.chat.side_effect = make_error(ErrorType.MODEL_UNAVAILABLE, "model gone", 404)
        p2 = FakeProvider("backup")
        p2.chat.return_value = make_response("backup model works")
        router = ProviderRouter([p1, p2])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert p2.chat.call_count == 1

    @pytest.mark.asyncio
    async def test_context_overflow_truncate_then_compact(self):
        """CONTEXT_OVERFLOW should truncate then compact then fail."""
        p = FakeProvider()
        p.chat.side_effect = [
            make_error(ErrorType.CONTEXT_OVERFLOW, "context too long"),
            make_error(ErrorType.CONTEXT_OVERFLOW, "still too long"),
            make_error(ErrorType.CONTEXT_OVERFLOW, "cannot"),
        ]
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError):
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert p.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        """Successful call should return immediately."""
        p = FakeProvider()
        p.chat.return_value = make_response("hello")
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.content[0].text == "hello"
        assert p.chat.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_guard_retry.py -v 2>&1 | head -20
```

Expected: FAIL — ContextGuard doesn't yet accept `provider_router` parameter

- [ ] **Step 3: Rewrite ContextGuard.async_guard_api_call**

Modify `agentd/context/context.py`:

First, add imports at the top:
```python
import asyncio
from agentd.providers.base import ErrorType, ProviderError
from agentd.providers.error_mapper import classify
```

Remove the old `import json` and `from typing import Any` if no longer used (keep the existing ones).

Replace the `__init__` method (lines 50-52):
```python
    def __init__(self, max_tokens: int = CONTEXT_SAFE_LIMIT, provider=None,
                 provider_router=None):
        self.max_tokens = max_tokens
        self._provider = provider  # backward compat
        self._router = provider_router  # new: ProviderRouter
```

Replace the `async_guard_api_call` method (lines 191-240) completely:

```python
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

        # 上下文溢出专用的两次重试计数器
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
                            print("  [guard] 上下文溢出，截断工具结果...")
                            current_messages = self._truncate_large_tool_results(current_messages)
                            overflow_attempt += 1
                        elif overflow_attempt == 1:
                            if self._provider is not None:
                                print("  [guard] 仍溢出，压缩对话历史...")
                                current_messages = await self.compact_history(current_messages)
                                overflow_attempt += 1
                            else:
                                raise
                        else:
                            raise

                    case ErrorType.RATE_LIMIT:
                        if attempt < 3:
                            wait = 2 ** attempt  # 1s, 2s, 4s
                            print(f"  [guard] 限流 ({err.status_code})，{wait}s 后退避重试...")
                            await asyncio.sleep(wait)
                        else:
                            raise

                    case ErrorType.AUTH_FAILURE:
                        if self._router is not None and self._router.switch():
                            new_model = self._router.current._model
                            print(f"  [guard] 认证失败，已切换到 {new_model}")
                        else:
                            raise

                    case ErrorType.SERVER_ERROR:
                        if attempt < 2:
                            wait = 2 * (attempt + 1)  # 2s, 4s
                            print(f"  [guard] 服务器错误 ({err.status_code})，{wait}s 后重试...")
                            await asyncio.sleep(wait)
                        else:
                            raise

                    case ErrorType.TIMEOUT:
                        if attempt < 2:
                            timeout_s = [30, 60, 120][attempt]
                            print(f"  [guard] 请求超时，增加到 {timeout_s}s 重试...")
                        else:
                            raise

                    case ErrorType.MODEL_UNAVAILABLE:
                        if self._router is not None and self._router.switch():
                            new_model = self._router.current._model
                            print(f"  [guard] 模型不可用，已切换到 {new_model}")
                        else:
                            raise

                    case ErrorType.UNKNOWN:
                        raise

        raise RuntimeError("async_guard_api_call: exhausted all retries")

    def _get_provider(self):
        """返回当前活跃的 provider（优先 router，回退到单 provider）。"""
        if self._router is not None:
            return self._router.current
        if self._provider is not None:
            return self._provider
        raise RuntimeError("No provider configured")
```

- [ ] **Step 4: Run guard retry tests**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/test_guard_retry.py -v
```

Expected: 10 passed

- [ ] **Step 5: Run ALL tests to confirm no regression**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/ -v
```

Expected: all tests pass (14 original + 17 error_mapper + 8 router + 10 guard = 49)

- [ ] **Step 6: Commit**

```bash
git add agentd/context/context.py tests/test_guard_retry.py
git commit -m "feat: rewrite async_guard_api_call with typed error strategy dispatch

- Replace string-matching with ErrorType enum matching
- 6 differentiated retry strategies: overflow, rate-limit, auth, server, timeout, model-unavailable
- UNKNOWN errors not retried
- User-visible prompts before each retry
- Backward compatible: accepts both provider= and provider_router=

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-error-classification-retry
---

### Task 6: AgentRunner 结构化错误传播

**Files:**
- Modify: `agentd/agent/runner.py:81-165` (modify `run_turn`)

**Interfaces:**
- Consumes: `ProviderError`, `ErrorType` from `agentd.providers.base`
- Modifies: `run_turn()` — catch `ProviderError`, distinguish recoverable vs fatal

- [ ] **Step 1: Modify run_turn error handling**

Modify `agentd/agent/runner.py`:

Add import at top (line 11 area):
```python
from agentd.providers.base import ErrorType, ProviderError
```

In `run_turn()`, add router reset at the start of the method (after line 93, before memory recall):
```python
        # 0. 重置 provider 到主（每 turn 重新开始）
        provider_router = self.container.get("provider_router")
        if provider_router:
            provider_router.reset()
```

Replace the error handling block (lines 126-136):

Old:
```python
            try:
                response = await self.guard.async_guard_api_call(
                    system=self._cached_system_prompt,
                    messages=messages,
                    tools=self.container.tools,
                )
                last_response = response
            except Exception as exc:
                logger.exception("[Runner] LLM 调用异常: %s", exc)
                self._rollback(messages)
                return ""
```

New:
```python
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
```

- [ ] **Step 2: Run all tests**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/ -v
```

Expected: all tests pass (49)

- [ ] **Step 3: Commit**

```bash
git add agentd/agent/runner.py
git commit -m "feat: structured ProviderError propagation in AgentRunner

- Router reset at start of each turn
- AUTH_FAILURE/MODEL_UNAVAILABLE → user-visible error with actionable message
- Other exhausted retries → rollback + silent return
- Backward compatible: bare Exception catch still works

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-error-classification-retry
---

### Task 7: Integration smoke test

**Files:**
- Modify: `tests/test_guard_retry.py` (add integration test)

**Interfaces:**
- Consumes: All modules from Tasks 1-6

- [ ] **Step 1: Add integration test**

Append to `tests/test_guard_retry.py`:

```python
class TestIntegration:
    """End-to-end error flow tests."""

    @pytest.mark.asyncio
    async def test_full_retry_chain(self):
        """A full chain: RATE_LIMIT → retry → SERVER_ERROR → retry → success."""
        p = FakeProvider()
        p.chat.side_effect = [
            make_error(ErrorType.RATE_LIMIT, "rate", 429),
            make_error(ErrorType.SERVER_ERROR, "server", 503),
            make_response("finally ok"),
        ]
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.content[0].text == "finally ok"
        assert p.chat.call_count == 3

    @pytest.mark.asyncio
    async def test_auth_failure_fatal(self):
        """AUTH_FAILURE with no backup → fatal."""
        p = FakeProvider()
        p.chat.side_effect = make_error(ErrorType.AUTH_FAILURE, "no key", 401)
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError) as exc_info:
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert exc_info.value.error_type == ErrorType.AUTH_FAILURE
```

- [ ] **Step 2: Run all tests**

```bash
cd c:/self/work/todo/ultimate_try && python -m pytest tests/ -v
```

Expected: all tests pass (49 + 2 = 51)

- [ ] **Step 3: Run build verification**

```bash
cd c:/self/work/todo/ultimate_try && python -c "from config.configs import get_config; from agentd.bootstrap.container import Container; from agentd.providers.error_mapper import classify; from agentd.providers.router import ProviderRouter; from agentd.providers.base import ErrorType, ProviderError; print('Build OK')"
```

Expected: `Build OK`

- [ ] **Step 4: Final commit**

```bash
git add tests/test_guard_retry.py
git commit -m "test: add integration tests for full retry chain and auth failure

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **Step 5: Update tasks.md — mark all tasks complete**

Update `openspec/changes/error-classification-retry/tasks.md` — check all `- [ ]` → `- [x]`
