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


class MockAPITimeoutError(Exception):
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
        err = classify(MockAPITimeoutError())
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


class TestErrorMapperPassthrough:
    """Already-typed ProviderError should pass through unchanged."""

    def test_provider_error_passthrough(self):
        orig = ProviderError(ErrorType.RATE_LIMIT, "test", 429)
        result = classify(orig)
        assert result is orig  # same object, not re-classified

    def test_provider_error_keeps_type(self):
        orig = ProviderError(ErrorType.CONTEXT_OVERFLOW, "test")
        result = classify(orig)
        assert result.error_type == ErrorType.CONTEXT_OVERFLOW


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
