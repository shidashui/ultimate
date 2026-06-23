## Approach

SQLite FTS5 全文索引。Python 标准库自带 sqlite3 模块，零外部依赖。

## Architecture

```
SessionStore.save_turn()
  ├── append_transcript(session_id, record)  # 现有：写入 JSONL
  └── SessionDB.index_turn(session_id, record)  # 新增：写入 FTS5

MemoryStore.hybrid_search(query)
  ├── _keyword_search()  # 现有：TF-IDF 搜索 MEMORY.md + daily
  ├── _vector_search()   # 现有：模拟向量搜索
  └── SessionDB.search(query)  # 新增：FTS5 BM25 搜索对话
  └── _merge_hybrid_results()  # 现有：合并 & 排序
```

## Key Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 引擎 | SQLite FTS5 | Python 标准库，零依赖，单文件部署 |
| 索引时机 | 同步写入 `save_turn()` | 简单可靠，~1ms 延迟可忽略 |
| 索引内容 | user + assistant 文本 | tool_use/tool_result 是结构化 JSON，搜索价值低 |
| 搜索结果合并 | 追加到 hybrid_search 结果末尾 | 保持 MemoryStore 接口不变，CLI 展示统一 |
| 数据库位置 | `workspace/.sessions/sessions.db` | 与 JSONL 同目录，统一管理 |

## Data Flow

```
用户输入 /search query
  → cli.handle_repl_command("/search")
  → MemoryStore.hybrid_search(query)
    → TF-IDF + Vector (现有两条通道)
    → SessionDB.search(query)  ← 新第三条通道
    → MMR re-rank → top_k
  → 展示合并结果
```

## FTS5 Schema

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    session_id,
    role,        -- 'user' or 'assistant'
    content,     -- 消息文本
    ts           -- 时间戳（用于排序）
);
```

## Error Handling

- 数据库文件不存在或损坏：降级为仅记忆搜索，不阻塞
- INSERT 失败：记录警告日志，不中断对话流
- search() SQL 错误：返回空列表

## Testing

- 单元测试：SessionDB 索引、搜索、空结果、SQL 注入防护
- 集成测试：SessionStore.save_turn() 触发索引写入
- 回归测试：hybrid_search() 在 SessionDB 不可用时仍返回记忆结果
