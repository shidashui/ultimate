---
comet_change: session-fts-search
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-23-session-fts-search
status: final
---

# Session FTS Search — 技术设计

## 架构

```
SessionStore.save_turn()
  ├── append_transcript(session_id, record)   # 现有：写入 JSONL
  └── if role in ("user", "assistant"):
      SessionDB.index_turn(sid, role, text, ts)  # 新增：写入 FTS5

MemoryStore.hybrid_search(query)
  ├── _keyword_search()    # 现有：TF-IDF
  ├── _vector_search()     # 现有：模拟向量
  ├── SessionDB.search(query)  # 新增：FTS5 BM25
  │   └── 结果标注 source: "session"
  └── 合并 + MMR → top_k

CLI /search
  → MemoryStore.hybrid_search()
  → 按 source 分组展示（记忆 / 对话）
```

## 组件

### SessionDB (`agentd/session/session_db.py`)

单一职责：FTS5 全文索引对话内容。

```python
class SessionDB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
            USING fts5(session_id, role, content, ts,
                       tokenize='unicode61')
        """)

    def index_turn(self, session_id: str, role: str,
                   content: str, ts: float) -> None: ...

    def search(self, query: str, limit: int = 5
              ) -> list[dict[str, Any]]: ...

    def close(self) -> None: ...
```

**FTS5 配置：**
- `tokenize='unicode61'`：支持 CJK 字符的 unicode 分词器
- 无外部内容表：FTS5 内部存储，简单可靠

**索引内容：** 仅 `user` 和 `assistant` 消息的文本。`tool_use` / `tool_result` 是结构化 JSON，搜索价值低。

**数据库位置：** `{workspace_dir}/.sessions/sessions.db`

### 集成改动

| 文件 | 改动 |
|------|------|
| `agentd/session/session_db.py` | **新建** — SessionDB 类 |
| `agentd/context/session.py` | 注入 SessionDB，save_turn 中调用 index_turn |
| `agentd/bootstrap/container.py` | 创建 SessionDB，传给 SessionStore |
| `agentd/memory/memory.py` | hybrid_search 接收可选 session_db 参数 |
| `cli/cli.py` | /search 展示合并结果，按 source 分组 |

### 结果数据结构

```python
# MemoryStore 现有格式
{"path": "MEMORY.md", "score": 0.95, "snippet": "..."}

# SessionDB 新增字段
{"path": "session:abc123", "score": 0.88, "snippet": "...",
 "source": "session", "session_id": "abc123", "role": "user", "ts": 1719000000.0}
```

## 错误处理

```
SessionDB.__init__
  └── sqlite3.connect 失败 → 记录警告，后续操作 no-op

SessionDB.index_turn
  └── INSERT 失败 → 静默 log，不抛异常

SessionDB.search
  └── SQL 错误 → 返回 []
  └── 数据库未初始化 → 返回 []

hybrid_search
  └── SessionDB 不可用 → 仅返回记忆搜索结果
```

## 测试策略

1. **单元测试** (`tests/test_session_db.py`)
   - `:memory:` SQLite，FTS5 建表 + INSERT + search
   - 中文分词匹配（"天气" → 匹配 "今天天气怎么样"）
   - 空结果、limit 截断
   - SQL 注入防护（FTS5 的 MATCH 语法自动转义）

2. **集成测试**
   - SessionStore.save_turn → SessionDB 索引写入
   - hybrid_search 合并记忆 + 对话结果

3. **回归测试**
   - MemoryStore 现有测试保持通过
   - SessionDB 不可用时 hybrid_search 降级返回记忆结果

## 风险

| 风险 | 概率 | 缓解 |
|------|------|------|
| FTS5 CJK 分词不准确 | 低 | unicode61 对 CJK 按单字切分，召回率高 |
| 数据库文件增长 | 中 | 轻量对话文本，长期可加 auto-vacuum |
| sqlite3 线程安全 | 低 | 单用户 REPL，无并发问题 |
