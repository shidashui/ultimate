"""Tests for audit logging."""
import json
import tempfile
from pathlib import Path
from agentd.tools.audit import AuditRecord, AuditLogger


class TestAuditRecord:
    def test_record_creation(self):
        r = AuditRecord(
            tool_name="bash",
            params={"command": "ls"},
            result_summary="file1\nfile2",
            duration_ms=12.5,
        )
        assert r.tool_name == "bash"
        assert r.blocked is False
        assert r.warnings == []

    def test_blocked_record(self):
        r = AuditRecord(
            tool_name="bash",
            params={"command": "rm -rf /"},
            result_summary="",
            duration_ms=0.0,
            blocked=True,
        )
        assert r.blocked is True


class TestAuditLogger:
    def test_log_writes_jsonl(self):
        d = tempfile.mkdtemp()
        al = AuditLogger(Path(d), session_id="test-session")
        al.log(AuditRecord("bash", {"command": "ls"}, "ok", 1.0))
        files = list(Path(d).glob("*.jsonl"))
        assert len(files) == 1
        content = files[0].read_text().strip()
        record = json.loads(content)
        assert record["tool"] == "bash"
        assert record["session"] == "test-session"
        assert record["result"] == "ok"

    def test_log_is_append(self):
        d = tempfile.mkdtemp()
        al = AuditLogger(Path(d), session_id="test")
        al.log(AuditRecord("bash", {}, "first", 1.0))
        al.log(AuditRecord("read_file", {}, "second", 2.0))
        files = list(Path(d).glob("*.jsonl"))
        lines = files[0].read_text().strip().splitlines()
        assert len(lines) == 2

    def test_recent_returns_latest(self):
        d = tempfile.mkdtemp()
        al = AuditLogger(Path(d), session_id="test")
        for i in range(10):
            al.log(AuditRecord("bash", {"n": i}, f"result-{i}", 1.0))
        records = al.recent(5)
        assert len(records) == 5

    def test_cleanup_deletes_old_files(self):
        d = tempfile.mkdtemp()
        al = AuditLogger(Path(d), session_id="test", max_days=0)
        al.log(AuditRecord("bash", {}, "test", 1.0))
        deleted = al.cleanup()
        # With max_days=0, the just-written file should be deleted
        assert deleted >= 1

    def test_log_write_failure_does_not_raise(self):
        # Use a read-only path that can't be created to simulate failure
        al = AuditLogger(Path("/nonexistent/readonly/path/audit"), session_id="test")
        # Should not raise
        al.log(AuditRecord("bash", {}, "test", 1.0))
