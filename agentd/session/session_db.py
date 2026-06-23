"""SessionDB — SQLite FTS5 全文索引对话内容。

轻量级封装，零外部依赖。职责：
  - 创建 FTS5 虚拟表（unicode61 分词，支持 CJK）
  - index_turn: 写入单条消息到索引
  - search: BM25 全文搜索，返回带来源标注的结果
"""
import re
import sqlite3
from pathlib import Path
from typing import Any


class SessionDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        try:
            self.conn = sqlite3.connect(str(db_path))
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
                USING fts5(session_id, role, content, ts,
                           tokenize='unicode61')
            """)
        except sqlite3.Error as e:
            print(f"WARNING: SessionDB init failed: {e}")
            self.conn = None

    @staticmethod
    def _prepare_for_fts(text: str) -> str:
        """Insert spaces around CJK characters so unicode61 tokenizer
        recognizes each character as a separate token."""
        return re.sub(r'([一-鿿㐀-䶿豈-﫿])',
                      r' \1 ', text)

    def index_turn(self, session_id: str, role: str,
                   content: str, ts: float) -> None:
        """将一条消息写入 FTS5 索引。失败时静默降级。"""
        if self.conn is None:
            return
        try:
            fts_content = self._prepare_for_fts(content)
            self.conn.execute(
                "INSERT INTO sessions_fts(session_id, role, content, ts) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, fts_content, ts),
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"WARNING: SessionDB index_turn failed: {e}")

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """BM25 全文搜索，返回按相关度排序的结果。SQL 错误时返回 []。"""
        if self.conn is None:
            return []
        try:
            fts_query = self._prepare_for_fts(query)
            cursor = self.conn.execute(
                "SELECT session_id, role, content, ts "
                "FROM sessions_fts WHERE content MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, limit),
            )
            results: list[dict[str, Any]] = []
            for row in cursor.fetchall():
                # Clean up FTS preprocessing: _prepare_for_fts surrounds each
                # CJK char with spaces. Remove spaces adjacent to CJK chars
                # to recover original text.
                snippet = row[2] if row[2] else ""
                cjk = r'一-鿿豈-﫿㐀-䶿'
                # collapse spaces between two CJK chars
                snippet = re.sub(rf'(?<=[{cjk}])\s+(?=[{cjk}])', '', snippet)
                # remove space immediately before CJK char
                snippet = re.sub(rf'\s+(?=[{cjk}])', '', snippet)
                # remove space immediately after CJK char
                snippet = re.sub(rf'(?<=[{cjk}])\s+', '', snippet)
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                results.append({
                    "path": f"session:{row[0]}",
                    "score": 1.0,
                    "snippet": snippet,
                    "source": "session",
                    "session_id": row[0],
                    "role": row[1],
                    "ts": row[3],
                })
            return results
        except sqlite3.Error:
            return []

    def close(self) -> None:
        """关闭数据库连接。"""
        if self.conn:
            self.conn.close()
            self.conn = None
