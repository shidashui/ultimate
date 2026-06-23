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
