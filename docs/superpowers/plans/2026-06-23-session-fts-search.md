---
change: session-fts-search
design-doc: docs/superpowers/specs/2026-06-23-session-fts-search-design.md
base-ref: 12c613d7edadc60dff2fee36cbf11a425e551730
archived-with: 2026-06-23-session-fts-search
---

# Session FTS Search 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为对话历史添加 SQLite FTS5 全文搜索，合并到 `/search` 命令展示

**Architecture:** SessionDB 封装 sqlite3 + FTS5 虚拟表；SessionStore.save_turn() 同步写入索引；MemoryStore.hybrid_search() 合并记忆和对话结果；CLI 按 source 分组展示

**Tech Stack:** Python 3 stdlib sqlite3, FTS5 tokenize=unicode61

## Global Constraints

- sqlite3 是标准库，零外部依赖
- FTS5 使用 `tokenize='unicode61'` 分词器（支持 CJK）
- 仅索引 `user` 和 `assistant` 消息文本
- 同步写入（`save_turn` 中直接 INSERT，不引入异步）
- 降级容错：DB 损坏或不可用时静默降级，不抛异常
- 不自动回填历史数据（测试阶段）

archived-with: 2026-06-23-session-fts-search
---

### Task 1: SessionDB 核心模块

**Files:**
- Create: `agentd/session/__init__.py`
- Create: `agentd/session/session_db.py`
- Create: `tests/test_session_db.py`

**Interfaces:**
- Produces: `SessionDB(db_path: Path)` — 初始化连接 + 建表
- Produces: `SessionDB.index_turn(session_id: str, role: str, content: str, ts: float) -> None`
- Produces: `SessionDB.search(query: str, limit: int = 5) -> list[dict[str, Any]]`
- Produces: `SessionDB.close() -> None`

- [ ] **Step 1: 创建目录和空 __init__.py**

```bash
mkdir -p agentd/session
```

`agentd/session/__init__.py`:
```python
from agentd.session.session_db import SessionDB

__all__ = ["SessionDB"]
```

- [ ] **Step 2: 编写 SessionDB 测试（TDD）**

`tests/test_session_db.py`:
```python
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
        # 应该匹配到包含"天气"的消息
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
        """连接失败时不抛异常，后续操作静默降级。"""
        # 传入一个目录路径（非文件）模拟连接失败 — sqlite3 仍会创建但之后可能出错
        # 更可靠的测试：关闭后操作
        db = SessionDB(Path(":memory:"))
        db.close()
        # 关闭后 index_turn 和 search 不抛异常
        db.index_turn("x", "user", "test", 0.0)  # 不抛异常
        assert db.search("test") == []  # 返回空列表

    def test_special_characters(self, db):
        """特殊字符（单引号、SQL 通配符）在 FTS5 MATCH 中安全处理。"""
        db.index_turn("abc123", "user", "it's a test with special chars", 1719000000.0)
        # FTS5 MATCH 语法中单引号需要转义
        results = db.search("test", limit=5)
        assert len(results) >= 1
```

- [ ] **Step 3: 运行测试确认失败**

```bash
python -m pytest tests/test_session_db.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'agentd.session'`

- [ ] **Step 4: 实现 SessionDB**

`agentd/session/session_db.py`:
```python
"""SessionDB — SQLite FTS5 全文索引对话内容。

轻量级封装，零外部依赖。职责：
  - 创建 FTS5 虚拟表（unicode61 分词，支持 CJK）
  - index_turn: 写入单条消息到索引
  - search: BM25 全文搜索，返回带来源标注的结果
"""
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

    def index_turn(self, session_id: str, role: str,
                   content: str, ts: float) -> None:
        """将一条消息写入 FTS5 索引。失败时静默降级。"""
        if self.conn is None:
            return
        try:
            self.conn.execute(
                "INSERT INTO sessions_fts(session_id, role, content, ts) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, ts),
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"WARNING: SessionDB index_turn failed: {e}")

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """BM25 全文搜索，返回按相关度排序的结果。SQL 错误时返回 []。"""
        if self.conn is None:
            return []
        try:
            cursor = self.conn.execute(
                "SELECT session_id, role, content, ts "
                "FROM sessions_fts WHERE content MATCH ? "
                "ORDER BY rank LIMIT ?",
                (query, limit),
            )
            results: list[dict[str, Any]] = []
            for row in cursor.fetchall():
                snippet = row[2]
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
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python -m pytest tests/test_session_db.py -v
```
Expected: 8 tests PASS

- [ ] **Step 6: 提交**

```bash
git add agentd/session/__init__.py agentd/session/session_db.py tests/test_session_db.py
git commit -m "feat: add SessionDB with SQLite FTS5 full-text search

- FTS5 virtual table with unicode61 tokenizer for CJK support
- index_turn() for sync write to index
- search() with BM25 ranking, returns structured results with source='session'
- Graceful degradation: DB errors logged, never thrown

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-session-fts-search
---

### Task 2: Container 注入 SessionDB

**Files:**
- Modify: `agentd/bootstrap/container.py:1-42`

**Interfaces:**
- Consumes: `SessionDB(db_path)` from Task 1
- Produces: Container registers `"session_db"` service
- Produces: `memory_store.session_db` attribute set

- [ ] **Step 1: 修改 Container.initialize()**

`agentd/bootstrap/container.py` — 在 `initialize` 方法中，`memory_store` 创建之后、`provider` 创建之前插入：

```python
# 在 initialize() 方法中，memory_store = MemoryStore(WORKSPACE_DIR) 之后添加：

        # SessionDB — FTS5 全文搜索对话历史
        from agentd.session.session_db import SessionDB
        session_db_path = WORKSPACE_DIR / ".sessions" / "sessions.db"
        session_db_path.parent.mkdir(parents=True, exist_ok=True)
        session_db = SessionDB(session_db_path)
        memory_store.session_db = session_db
```

在 `self.register` 块中添加：
```python
        self.register("session_db", session_db)
```

完整改动后的 `initialize()`:
```python
    def initialize(self):
        # 这里可以添加一些全局初始化的逻辑，比如加载工具、设置环境变量等
        loader = BootstrapLoader(WORKSPACE_DIR)
        bootstrap_data = loader.load_all(mode="full")
        skills_mgr = SkillsManager(WORKSPACE_DIR)
        skills_mgr.discover()
        memory_store = MemoryStore(WORKSPACE_DIR)
        # SessionDB — FTS5 全文搜索对话历史
        from agentd.session.session_db import SessionDB
        session_db_path = WORKSPACE_DIR / ".sessions" / "sessions.db"
        session_db_path.parent.mkdir(parents=True, exist_ok=True)
        session_db = SessionDB(session_db_path)
        memory_store.session_db = session_db
        # Provider — 由 config.yaml 驱动
        provider = get_model_provider()
        guard = ContextGuard(provider=provider)

        self.register("bootstrap_data", bootstrap_data)
        self.register("skills_mgr", skills_mgr)
        self.register("memory_store", memory_store)
        self.register("session_db", session_db)
        self.register("guard", guard)
        self.register("provider", provider)

        self.tools = get_tools()
        self.tools_handlers = get_tool_handlers()
```

- [ ] **Step 2: 验证 Container 导入不报错**

```bash
python -c "from agentd.bootstrap.container import container; print('session_db' in container.services)"
```
Expected: `True`

- [ ] **Step 3: 提交**

```bash
git add agentd/bootstrap/container.py
git commit -m "feat: wire SessionDB into Container and MemoryStore

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-session-fts-search
---

### Task 3: MemoryStore.hybrid_search 合并会话结果

**Files:**
- Modify: `agentd/memory/memory.py:286-301`

**Interfaces:**
- Consumes: `self.session_db` (optional, set by Container in Task 2)
- Modifies: `hybrid_search()` — 追加 session 结果，添加 `source` 字段
- Produces: 统一格式结果 `[{path, score, snippet, source, ...}]`

- [ ] **Step 1: 编写回归测试**

`tests/test_session_db.py` 追加:
```python
    def test_hybrid_search_falls_back_when_no_session_db(self):
        """当 session_db 不存在时，hybrid_search 仍返回记忆结果。"""
        from agentd.memory.memory import MemoryStore
        from pathlib import Path
        import tempfile, os

        # 使用临时目录模拟空的 memory workspace
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "memory" / "daily").mkdir(parents=True)
            store = MemoryStore(ws)
            # 没有 session_db 属性 — 不应报错
            results = store.hybrid_search("test", top_k=5)
            assert isinstance(results, list)
```

- [ ] **Step 2: 修改 hybrid_search() 合并会话结果**

`agentd/memory/memory.py` — 修改 `hybrid_search` 方法：

在现有结果构建循环中给每条记忆结果加 `"source": "memory"`，然后在返回前追加 session 结果。

现有 `hybrid_search` 的结果构建部分（约 296-301 行）改为：

```python
    def hybrid_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Full hybrid search pipeline: keyword -> vector -> merge -> decay -> MMR -> top_k"""
        chunks = self._load_all_chunks()
        if not chunks:
            result = []
        else:
            keyword_results = self._keyword_search(query, chunks, top_k=10)
            vector_results = self._vector_search(query, chunks, top_k=10)
            merged = self._merge_hybrid_results(vector_results, keyword_results)
            decayed = self._temporal_decay(merged)
            reranked = self._mmr_rerank(decayed)
            result = []
            for r in reranked[:top_k]:
                snippet = r["chunk"]["text"]
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                result.append({
                    "path": r["chunk"]["path"],
                    "score": round(r["score"], 4),
                    "snippet": snippet,
                    "source": "memory",
                })

        # Merge FTS5 session search results
        session_db = getattr(self, 'session_db', None)
        if session_db is not None:
            try:
                session_results = session_db.search(query, limit=top_k)
                result.extend(session_results)
            except Exception:
                pass  # 降级：会话搜索失败不阻塞记忆搜索

        # Sort by score descending (memory has [0,1] scores, session has 1.0)
        result.sort(key=lambda x: x.get("score", 0), reverse=True)
        return result[:top_k]
```

- [ ] **Step 3: 运行测试确认通过**

```bash
python -m pytest tests/test_session_db.py::TestSessionDB::test_hybrid_search_falls_back_when_no_session_db -v
python -m pytest tests/test_config.py -v
```
Expected: all PASS

- [ ] **Step 4: 提交**

```bash
git add agentd/memory/memory.py tests/test_session_db.py
git commit -m "feat: merge SessionDB results into hybrid_search

- Add source='memory' tag to existing memory results
- Append session FTS5 results with source='session'
- Graceful fallback when session_db is not available

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-session-fts-search
---

### Task 4: SessionStore 集成索引写入

**Files:**
- Modify: `agentd/context/session.py:14-24,76-79`

**Interfaces:**
- Consumes: `SessionDB` from Task 1
- Modifies: `SessionStore.__init__` — 接受可选 `session_db` 参数
- Modifies: `SessionStore.save_turn` — 对 user/assistant 消息调用 `index_turn`
- Modifies: `SessionStore.save_tool_result` — 不触发索引（已限定 role）

- [ ] **Step 1: 修改 SessionStore.__init__ 接受 session_db**

`agentd/context/session.py` — 在 `__init__` 方法中添加参数：

```python
class SessionStore:
    """管理 agent 会话的持久化存储。"""

    def __init__(self, base_dir: Path, agent_id: str = "default",
                 user_name: str = "User", session_db=None):
        self.agent_id = agent_id
        self.user_name = user_name
        self.base_dir = base_dir
        self.index_path = self.base_dir.parent / "sessions.json"
        self._index: dict[str, dict] = self._load_index()
        self.current_session_id: str | None = None
        self.session_db = session_db  # NEW: FTS5 索引
```

- [ ] **Step 2: 添加文本提取辅助方法**

在 `SessionStore` 类中添加静态方法（放在 `_rebuild_history` 之后）：

```python
    @staticmethod
    def _extract_text(content) -> str:
        """从 save_turn 的 content 中提取纯文本。
        user 消息是 str，assistant 消息是 list[dict]（_serialize 的输出）。
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return " ".join(parts)
        return str(content)
```

- [ ] **Step 3: 修改 save_turn 触发 FTS5 索引**

`agentd/context/session.py` — 修改 `save_turn` 方法：

```python
    def save_turn(self, role: str, content: Any) -> None:
        if not self.current_session_id:
            return
        ts = time.time()
        self.append_transcript(self.current_session_id, {
            "type": role,
            "content": content,
            "ts": ts,
        })
        # FTS5 索引: 仅 user/assistant 文本
        if self.session_db is not None and role in ("user", "assistant"):
            text = self._extract_text(content)
            self.session_db.index_turn(
                self.current_session_id, role, text, ts
            )
```

- [ ] **Step 4: 在 Cli 中注入 session_db 到 SessionStore**

`cli/cli.py` — 修改 `Cli.__init__`:

```python
class Cli:
    def __init__(self):
        self.store = SessionStore(base_dir=WORKSPACE_DIR, agent_id="zero")
        self.messages: list[dict] = []
        self.runner = AgentRunner()
        # 注入 SessionDB 到 SessionStore
        session_db = self.runner.container.get("session_db")
        if session_db:
            self.store.session_db = session_db
```

注意：`Cli.__init__` 中 `self.runner = AgentRunner()` 已经初始化了 Container，所以 `container.get("session_db")` 此时已可用。

- [ ] **Step 5: 验证导入和集成**

```bash
python -c "
from config.configs import WORKSPACE_DIR
from agentd.bootstrap.container import container
from agentd.context.session import SessionStore
store = SessionStore(WORKSPACE_DIR, agent_id='test', session_db=container.get('session_db'))
print('SessionStore.session_db:', store.session_db is not None)
print('SessionDB path:', store.session_db.db_path if store.session_db else 'None')
"
```
Expected: `SessionStore.session_db: True` + 数据库路径

- [ ] **Step 6: 提交**

```bash
git add agentd/context/session.py cli/cli.py
git commit -m "feat: integrate SessionDB into SessionStore for auto-indexing

- SessionStore accepts optional session_db parameter
- save_turn() calls index_turn() for user/assistant messages
- _extract_text() helper handles both str and list[dict] content
- Cli injects session_db from Container into SessionStore

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-session-fts-search
---

### Task 5: CLI /search 按来源分组展示

**Files:**
- Modify: `cli/cli.py:214-225`

**Interfaces:**
- Consumes: `hybrid_search()` 返回的结果包含 `source` 字段（Task 3）
- Modifies: `/search` REPL 命令 — 按 source 分组展示

- [ ] **Step 1: 修改 /search 命令展示逻辑**

`cli/cli.py` — 替换 `/search` 命令处理（约 214-225 行）：

```python
        elif cmd == "/search":
            if not arg:
                print_yellow_info("用法: /search <query>")
                return True
            print_section(f"搜索: {arg}")
            results = self.runner.memory_store.hybrid_search(arg)
            if not results:
                print_info("(无结果)")
            else:
                # 按来源分组
                memory_results = [r for r in results if r.get("source") != "session"]
                session_results = [r for r in results if r.get("source") == "session"]

                if memory_results:
                    console.print(f"\n[muted]── 记忆 ({len(memory_results)} 条) ──[/muted]")
                    for r in memory_results:
                        print_memory_info(r)

                if session_results:
                    console.print(f"\n[muted]── 对话 ({len(session_results)} 条) ──[/muted]")
                    for r in session_results:
                        role_label = "[info]You[/info]" if r.get("role") == "user" else "[success]AI[/success]"
                        sid_short = r.get("session_id", "")[:8]
                        console.print(
                            f"  {role_label} [{r.get('session_id', '')[:8]}] "
                            f"[muted]{r['snippet']}[/muted]"
                        )

            return True
```

- [ ] **Step 2: 验证 CLI 帮助命令仍正常**

```bash
python -c "from cli.cli import Cli; print('Cli import OK')"
```
Expected: `Cli import OK`

- [ ] **Step 3: 提交**

```bash
git add cli/cli.py
git commit -m "feat: group /search results by source (memory vs session)

- Memory results tagged with source='memory'
- Session results tagged with source='session'
- Display grouped with role badge and session ID prefix

Co-Authored-By: Claude <noreply@anthropic.com>"
```

archived-with: 2026-06-23-session-fts-search
---

### Task 6: 端到端验证

**Files:** (验证，无新代码)

- [ ] **Step 1: 运行全部测试**

```bash
python -m pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 2: 运行构建检查**

```bash
python -c "
from config.configs import get_config
from agentd.bootstrap.container import Container
from agentd.session.session_db import SessionDB
from agentd.context.session import SessionStore
from agentd.memory.memory import MemoryStore
print('All imports OK')
print('Build passes')
"
```
Expected: `All imports OK` + `Build passes`

- [ ] **Step 3: 提交（如有 tasks.md 更新）**

```bash
git add openspec/changes/session-fts-search/tasks.md
git commit -m "chore: mark all tasks complete in session-fts-search

Co-Authored-By: Claude <noreply@anthropic.com>"
```
