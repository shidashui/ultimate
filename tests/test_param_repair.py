"""Tests for tool call parameter validation & auto-repair."""
import pytest
from agentd.tools.param_repair import validate_and_repair
from agentd.agent.runner import AgentRunner
from agentd.bootstrap import set_current_container


# ── fixtures ──────────────────────────────────────────────

BASH_SCHEMA = {
    "command": {"type": "string", "description": "The shell command."},
    "timeout": {"type": "integer", "description": "Timeout in seconds."},
}

MEMORY_WRITE_SCHEMA = {
    "content": {"type": "string", "description": "The fact to remember."},
    "category": {"type": "string", "description": "Category."},
}

NO_PARAM_SCHEMA = {}


# ── type coercion ─────────────────────────────────────────

class TestTypeCoercion:
    def test_str_to_int(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": "30"}, BASH_SCHEMA
        )
        assert repaired["timeout"] == 30
        assert isinstance(repaired["timeout"], int)
        assert any("coerced" in w for w in warnings)

    def test_int_to_str(self):
        schema = {"command": {"type": "string"}}
        repaired, warnings = validate_and_repair({"command": 42}, schema)
        assert repaired["command"] == "42"
        assert isinstance(repaired["command"], str)
        assert any("coerced" in w for w in warnings)

    def test_float_to_int(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": 3.7}, BASH_SCHEMA
        )
        assert repaired["timeout"] == 3
        assert isinstance(repaired["timeout"], int)
        assert any("coerced" in w for w in warnings)

    def test_already_correct_type_no_warning(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": 30}, BASH_SCHEMA
        )
        assert repaired == {"command": "ls", "timeout": 30}
        assert warnings == []

    def test_bool_str_coercion_true(self):
        schema = {"verbose": {"type": "boolean"}}
        repaired, warnings = validate_and_repair({"verbose": "true"}, schema)
        assert repaired["verbose"] is True
        assert any("coerced" in w for w in warnings)

    def test_bool_str_coercion_false(self):
        schema = {"verbose": {"type": "boolean"}}
        repaired, _ = validate_and_repair({"verbose": "false"}, schema)
        assert repaired["verbose"] is False

    def test_coercion_failure_reports_error(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": "abc"}, BASH_SCHEMA
        )
        assert repaired == {}
        assert any("cannot coerce" in w for w in warnings)

    def test_bool_to_int_coercion(self):
        """bool is subclass of int, need explicit coerce."""
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": True}, BASH_SCHEMA
        )
        assert repaired["timeout"] == 1
        assert any("bool → int" in w for w in warnings)


# ── extra param removal ───────────────────────────────────

class TestExtraParamRemoval:
    def test_extra_param_removed(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "hallucinated": "x"}, BASH_SCHEMA
        )
        assert "hallucinated" not in repaired
        assert "command" in repaired
        assert any("unknown param" in w for w in warnings)


# ── default value filling ─────────────────────────────────

def _dummy_handler(command, timeout=30):
    pass

def _dummy_no_defaults(command, timeout):
    pass


class TestDefaultFilling:
    def test_missing_optional_filled(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls"}, BASH_SCHEMA, _dummy_handler
        )
        assert repaired["timeout"] == 30
        assert any("filled default" in w for w in warnings)

    def test_missing_required_reports_error(self):
        repaired, warnings = validate_and_repair(
            {}, BASH_SCHEMA, _dummy_no_defaults
        )
        assert repaired == {}
        assert any("missing required" in w for w in warnings)

    def test_multiple_missing_required(self):
        repaired, warnings = validate_and_repair(
            {}, BASH_SCHEMA, _dummy_no_defaults
        )
        missing = [w for w in warnings if "missing required" in w]
        assert len(missing) >= 2

    def test_fill_only_defaults_not_required(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls"}, BASH_SCHEMA, _dummy_handler
        )
        assert repaired["command"] == "ls"
        assert repaired["timeout"] == 30


# ── empty input / no-param tools ──────────────────────────

class TestEdgeCases:
    def test_empty_input_all_defaults(self):
        def handler(verbose=False, timeout=10):
            pass
        schema = {
            "verbose": {"type": "boolean"},
            "timeout": {"type": "integer"},
        }
        repaired, warnings = validate_and_repair({}, schema, handler)
        assert repaired == {"verbose": False, "timeout": 10}

    def test_no_param_tool(self):
        repaired, warnings = validate_and_repair({}, NO_PARAM_SCHEMA)
        assert repaired == {}
        assert warnings == []

    def test_none_schema_passthrough(self):
        repaired, warnings = validate_and_repair({"any": "thing"}, None)
        assert repaired == {"any": "thing"}
        assert warnings == []

    def test_multiple_issues(self):
        repaired, warnings = validate_and_repair(
            {"command": "ls", "timeout": "5.0", "extra": "x"},
            BASH_SCHEMA, _dummy_handler
        )
        assert repaired["timeout"] == 5
        assert "extra" not in repaired
        assert "command" in repaired
        assert len(warnings) >= 2  # coercion + extra removal

    def test_unknown_schema_type_passthrough(self):
        """Schema with type not in mapping — value passes through unchanged."""
        schema = {"data": {"type": "unknown-type"}}
        repaired, warnings = validate_and_repair({"data": [1, 2, 3]}, schema)
        assert repaired["data"] == [1, 2, 3]
        assert warnings == []

    def test_handler_none_skips_defaults(self):
        """handler=None — no default filling attempted."""
        repaired, warnings = validate_and_repair(
            {"command": "ls"}, BASH_SCHEMA, handler=None
        )
        assert "timeout" not in repaired
        assert "command" in repaired


# ── integration: process_tool_call ─────────────────────────

class TestProcessToolCallIntegration:
    """End-to-end: malformed input → process_tool_call with real handlers."""

    @pytest.fixture(autouse=True)
    def _setup_container(self):
        """Set the container context so handlers like memory_write work."""
        runner = AgentRunner("test")
        set_current_container(runner.container)
        yield
        set_current_container(None)

    def test_repaired_bash_timeout(self):
        runner = AgentRunner("test")
        set_current_container(runner.container)
        try:
            result = runner.process_tool_call("bash", {"command": "echo hi", "timeout": "5"})
            assert "hi" in result
            assert "Error" not in result
        finally:
            set_current_container(None)

    def test_missing_required_command(self):
        runner = AgentRunner("test")
        result = runner.process_tool_call("bash", {})
        assert "Error" in result
        assert "command" in result.lower()

    def test_unknown_tool(self):
        runner = AgentRunner("test")
        result = runner.process_tool_call("nonexistent", {})
        assert "Unknown tool" in result

    def test_get_current_time_no_params(self):
        runner = AgentRunner("test")
        result = runner.process_tool_call("get_current_time", {})
        assert "Error" not in result
        assert "UTC" in result

    def test_memory_write_default_category(self):
        runner = AgentRunner("test")
        set_current_container(runner.container)
        try:
            result = runner.process_tool_call("memory_write", {"content": "test fact"})
            # Should succeed (fills default category="general")
            assert "Error" not in result
        finally:
            set_current_container(None)

    def test_uncoercable_param(self):
        """timeout='abc' can't be coerced to int → diagnostic error."""
        runner = AgentRunner("test")
        result = runner.process_tool_call("bash", {"command": "ls", "timeout": "abc"})
        assert "Error" in result
        assert "timeout" in result.lower()
        assert "cannot coerce" in result.lower()
        assert "cannot coerce" in result.lower()
