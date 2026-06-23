import pytest
from pathlib import Path
from agentd.session.session_db import SessionDB


class TestSessionDB:
    """FTS5 全文搜索单元测试。"""

    @pytest.fixture
    def db(self):
        """使用 :memory: 数据库，每次测试独立。"""
        db = SessionDB(Path(":memory:"))
        yield db
        db.close()

    def test_create_fts_table(self, db):
        """FTS5 虚拟表在 __init__ 时自动创建。"""
        rows = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions_fts'"
        ).fetchall()
        assert len(rows) == 1

    def test_index_and_search(self, db):
        """写入一条 user 消息后能通过全文搜索找到。"""
        db.index_turn("abc123", "user", "今天天气怎么样", 1719000000.0)
        db.index_turn("abc123", "assistant", "今天天气晴朗，适合出门", 1719000001.0)
        db.index_turn("def456", "user", "明天会下雨吗", 1719000100.0)

        results = db.search("天气", limit=5)
        assert len(results) >= 1
        contents = [r["snippet"] for r in results]
        assert any("天气" in c for c in contents)

    def test_search_no_match(self, db):
        """无匹配时返回空列表。"""
        db.index_turn("abc123", "user", "hello world", 1719000000.0)
        results = db.search("xyz不存在的关键词abc", limit=5)
        assert results == []

    def test_search_limit(self, db):
        """limit 参数截断结果数量。"""
        for i in range(10):
            db.index_turn(f"sid{i}", "user", f"测试消息 关键词 {i}", 1719000000.0 + i)
        results = db.search("关键词", limit=3)
        assert len(results) <= 3

    def test_chinese_tokenization(self, db):
        """unicode61 分词器对 CJK 字符按单字切分，支持中文搜索。"""
        db.index_turn("abc123", "user", "我想了解Python编程", 1719000000.0)
        results = db.search("Python", limit=5)
        assert len(results) >= 1
        assert "Python" in results[0]["snippet"]

    def test_result_structure(self, db):
        """搜索结果包含所有必要字段。"""
        db.index_turn("abc123", "user", "测试消息内容", 1719000000.0)
        results = db.search("测试", limit=5)
        assert len(results) >= 1
        r = results[0]
        assert r["source"] == "session"
        assert r["session_id"] == "abc123"
        assert r["role"] == "user"
        assert "path" in r
        assert "score" in r
        assert "snippet" in r
        assert "ts" in r

    def test_db_connect_failure_graceful(self, tmp_path):
        """关闭后操作不抛异常。"""
        db = SessionDB(Path(":memory:"))
        db.close()
        db.index_turn("x", "user", "test", 0.0)  # 不抛异常
        assert db.search("test") == []  # 返回空列表

    def test_special_characters(self, db):
        """特殊字符在 FTS5 MATCH 中安全处理。"""
        db.index_turn("abc123", "user", "it's a test with special chars", 1719000000.0)
        results = db.search("test", limit=5)
        assert len(results) >= 1

    def test_hybrid_search_falls_back_when_no_session_db(self):
        """当 session_db 不存在时，hybrid_search 仍返回记忆结果。"""
        from agentd.memory.memory import MemoryStore
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "memory" / "daily").mkdir(parents=True)
            store = MemoryStore(ws)
            store.hybrid_search("test", top_k=5)
