"""Tool call audit logging — JSONL format, daily rotation."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    """Single tool call audit entry."""
    tool_name: str
    params: dict
    result_summary: str   # first 200 chars
    duration_ms: float
    warnings: list[str] = field(default_factory=list)
    blocked: bool = False

    # Filled by logger at write time
    timestamp: str = ""
    session_id: str = ""


class AuditLogger:
    """JSONL audit log with daily rotation and auto-cleanup.

    Thread-safe: uses a lock for concurrent writes.
    """

    def __init__(self, log_dir: Path, session_id: str = "", max_days: int = 30):
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._session_id = session_id
        self._max_days = max_days
        self._lock = threading.Lock()

    # ── public API ──────────────────────────────────────────

    def log(self, record: AuditRecord) -> None:
        """Append one JSON line to today's log file."""
        record.timestamp = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        record.session_id = self._session_id
        line = json.dumps({
            "ts": record.timestamp,
            "session": record.session_id,
            "tool": record.tool_name,
            "params": record.params,
            "result": record.result_summary[:200],
            "dur_ms": round(record.duration_ms, 1),
            "warnings": record.warnings,
            "blocked": record.blocked,
        }, ensure_ascii=False)
        try:
            with self._lock:
                filepath = self._today_file()
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            logger.error(
                "[audit] failed to write audit log for %s", record.tool_name,
                exc_info=True
            )

    def recent(self, n: int = 100) -> list[dict]:
        """Read up to N most recent records across all recent log files."""
        records: list[dict] = []
        files = sorted(self._log_dir.glob("*.jsonl"), reverse=True)
        for fp in files:
            if len(records) >= n:
                break
            try:
                lines = fp.read_text(encoding="utf-8").strip().splitlines()
                for line in reversed(lines):
                    if not line:
                        continue
                    records.append(json.loads(line))
                    if len(records) >= n:
                        break
            except Exception:
                continue
        return list(reversed(records))

    def cleanup(self) -> int:
        """Delete log files older than max_days. Returns count of deleted files."""
        import time
        cutoff = time.time() - (self._max_days * 86400)
        deleted = 0
        for fp in self._log_dir.glob("*.jsonl"):
            try:
                if fp.stat().st_mtime < cutoff:
                    fp.unlink()
                    deleted += 1
            except Exception:
                continue
        return deleted

    # ── internal ────────────────────────────────────────────

    def _today_file(self) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._log_dir / f"{today}.jsonl"
