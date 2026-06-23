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
        self._model = name
        self._chat = AsyncMock()
        self._chat.return_value = make_response("default")

    async def chat(self, messages, system, tools=None, **kwargs):
        return await self._chat(messages=messages, system=system,
                                tools=tools, **kwargs)

    def estimate_tokens(self, text):
        return len(text) // 4


class TestGuardRetry:
    """Test that each ErrorType triggers the correct retry behavior."""

    @pytest.mark.asyncio
    async def test_unknown_error_not_retried(self):
        """UNKNOWN errors should be raised immediately, no retry."""
        p = FakeProvider()
        p._chat.side_effect = make_error(ErrorType.UNKNOWN, "weird error")
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError) as exc_info:
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert exc_info.value.error_type == ErrorType.UNKNOWN
        assert p._chat.call_count == 1  # no retry

    @pytest.mark.asyncio
    async def test_rate_limit_exponential_backoff(self):
        """RATE_LIMIT should retry with exponential backoff."""
        p = FakeProvider()
        p._chat.side_effect = [
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
        assert p._chat.call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limit_exhausted(self):
        """After 3 RATE_LIMIT retries, should raise."""
        p = FakeProvider()
        # After 3 retries (attempts 0,1,2), the 4th call triggers raise.
        # We need 4 items so the mock doesn't exhaust before guard handles it.
        p._chat.side_effect = [
            make_error(ErrorType.RATE_LIMIT, "too fast", 429),
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
        # 3 retry calls + 1 final call that raises
        assert p._chat.call_count >= 3

    @pytest.mark.asyncio
    async def test_auth_failure_switches_provider(self):
        """AUTH_FAILURE should switch to backup provider."""
        p1 = FakeProvider("main")
        p1._chat.side_effect = make_error(ErrorType.AUTH_FAILURE, "bad key", 401)
        p2 = FakeProvider("backup")
        p2._chat.return_value = make_response("backup works")
        router = ProviderRouter([p1, p2])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert p2._chat.call_count == 1

    @pytest.mark.asyncio
    async def test_auth_failure_no_backup_raises(self):
        """AUTH_FAILURE with no backup should raise."""
        p = FakeProvider()
        p._chat.side_effect = make_error(ErrorType.AUTH_FAILURE, "bad key", 401)
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError) as exc_info:
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert exc_info.value.error_type == ErrorType.AUTH_FAILURE
        assert p._chat.call_count == 1

    @pytest.mark.asyncio
    async def test_server_error_linear_retry(self):
        """SERVER_ERROR should retry with linear backoff."""
        p = FakeProvider()
        p._chat.side_effect = [
            make_error(ErrorType.SERVER_ERROR, "500", 500),
            make_response("ok"),
        ]
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert p._chat.call_count == 2

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

        p._chat.side_effect = fake_chat
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
        p1._chat.side_effect = make_error(ErrorType.MODEL_UNAVAILABLE, "model gone", 404)
        p2 = FakeProvider("backup")
        p2._chat.return_value = make_response("backup model works")
        router = ProviderRouter([p1, p2])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.stop_reason == "end_turn"
        assert p2._chat.call_count == 1

    @pytest.mark.asyncio
    async def test_context_overflow_truncate_then_compact(self):
        """CONTEXT_OVERFLOW should truncate then compact then fail.

        Note: compact_history internally calls provider.chat() for the summary,
        which consumes an extra side_effect item. The guard retries overflow
        twice (truncate, compact) then raises on the third.
        """
        p = FakeProvider()
        # overflow-1 (guard) → truncate
        # overflow-2 (guard) → calls compact_history
        #   overflow-2a (compact_history internal call) — summary attempt
        # overflow-3 (guard) → raise
        p._chat.side_effect = [
            make_error(ErrorType.CONTEXT_OVERFLOW, "overflow 1"),
            make_error(ErrorType.CONTEXT_OVERFLOW, "overflow 2"),
            make_error(ErrorType.CONTEXT_OVERFLOW, "compact internal"),
            make_error(ErrorType.CONTEXT_OVERFLOW, "overflow 3"),
        ]
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError):
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        # Guard calls at least 3 times; compact_history may add more
        assert p._chat.call_count >= 3

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        """Successful call should return immediately."""
        p = FakeProvider()
        p._chat.return_value = make_response("hello")
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        result = await guard.async_guard_api_call(
            system="", messages=[{"role": "user", "content": "hi"}],
        )
        assert result.content[0].text == "hello"
        assert p._chat.call_count == 1


class TestIntegration:
    """End-to-end error flow tests."""

    @pytest.mark.asyncio
    async def test_full_retry_chain(self):
        """A full chain: RATE_LIMIT → retry → SERVER_ERROR → retry → success."""
        p = FakeProvider()
        p._chat.side_effect = [
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
        assert p._chat.call_count == 3

    @pytest.mark.asyncio
    async def test_auth_failure_fatal(self):
        """AUTH_FAILURE with no backup → fatal."""
        p = FakeProvider()
        p._chat.side_effect = make_error(ErrorType.AUTH_FAILURE, "no key", 401)
        router = ProviderRouter([p])
        guard = ContextGuard(provider_router=router)

        with pytest.raises(ProviderError) as exc_info:
            await guard.async_guard_api_call(
                system="", messages=[{"role": "user", "content": "hi"}],
            )
        assert exc_info.value.error_type == ErrorType.AUTH_FAILURE
