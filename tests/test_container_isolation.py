"""Tests for per-session container isolation."""
import pytest
from agentd.bootstrap import Container, set_current_container, get_current_container
from agentd.agent.runner import AgentRunner


class TestContextVar:
    """ContextVar set/get/clear behavior."""

    def test_set_and_get(self):
        c = Container("test")
        set_current_container(c)
        try:
            assert get_current_container() is c
            assert get_current_container().session_id == "test"
        finally:
            set_current_container(None)

    def test_get_without_set_raises(self):
        set_current_container(None)
        with pytest.raises(RuntimeError, match="No container set"):
            get_current_container()

    def test_set_none_then_get_raises(self):
        set_current_container(None)
        with pytest.raises(RuntimeError, match="No container set"):
            get_current_container()


class TestContainerIsolation:
    """Two AgentRunners have independent containers."""

    def test_independent_containers(self):
        r1 = AgentRunner("session-a")
        r2 = AgentRunner("session-b")

        assert r1.container is not r2.container
        assert r1.container.session_id == "session-a"
        assert r2.container.session_id == "session-b"

    def test_independent_services(self):
        r1 = AgentRunner("a")
        r2 = AgentRunner("b")

        assert r1.guard is not r2.guard
        assert r1.memory_store is not r2.memory_store
        assert r1.skills_mgr is not r2.skills_mgr

    def test_guard_has_own_router(self):
        r1 = AgentRunner("a")
        r2 = AgentRunner("b")

        router1 = r1.container.get("provider_router")
        router2 = r2.container.get("provider_router")
        assert router1 is not router2

    def test_default_session_id_is_none(self):
        r = AgentRunner()
        assert r.container.session_id is None

    def test_tools_handlers_property(self):
        r = AgentRunner()
        assert isinstance(r.tools_handlers, dict)
        assert len(r.tools_handlers) > 0


class TestContextVarCleanup:
    """ContextVar is cleared after run_turn, even on error."""

    @pytest.mark.asyncio
    async def test_contextvar_cleared_after_error(self):
        r = AgentRunner("test")
        set_current_container(None)

        try:
            await r.run_turn(
                user_input="hi",
                messages=[],
                store=None,
                channel="terminal",
            )
        except Exception:
            pass

        # ContextVar should be cleared by finally block
        with pytest.raises(RuntimeError, match="No container set"):
            get_current_container()


class TestToolFunctions:
    """Tool functions use ContextVar, not global import."""

    def test_memory_tools_use_contextvar(self):
        """memory_tools import should not fail (no container needed for import)."""
        from agentd.tools.memory_tools import tool_memory_write, tool_memory_search
        assert callable(tool_memory_write)
        assert callable(tool_memory_search)

    def test_skill_tools_use_contextvar(self):
        """skill_tools import should not fail."""
        from agentd.tools.skill_tools import tool_skill_invoke
        assert callable(tool_skill_invoke)

    def test_skill_invoke_called_outside_run_turn_raises(self):
        """Calling skill_invoke outside run_turn should fail with clear error."""
        from agentd.tools.skill_tools import tool_skill_invoke
        set_current_container(None)
        with pytest.raises(RuntimeError, match="No container set"):
            tool_skill_invoke("nonexistent")
