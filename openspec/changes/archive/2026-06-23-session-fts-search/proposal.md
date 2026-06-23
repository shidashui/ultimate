## Why

当前 `/search` 只能搜索 MEMORY.md 和每日日志（memory/daily/*.jsonl），对话历史虽然已完整持久化到 `SessionStore`（workspace/.sessions/.../*.jsonl），但没有索引层，用户无法搜索以前的对话内容。需要一个轻量级全文搜索层覆盖对话历史，与现有记忆搜索合并展示。

## What Changes

- 新增 `agentd/session/session_db.py`：`SessionDB` 类，基于 SQLite + FTS5 虚拟表存储和索引对话内容
- 修改 `agentd/context/session.py`：`SessionStore.save_turn()` 同步写入 FTS5 索引
- 修改 `agentd/memory/memory.py`：`hybrid_search()` 合并 SessionDB 搜索结果
- 修改 `cli/cli.py`：`/search` 命令展示合并后的搜索结果（记忆 + 对话）
- 新增 `tests/test_session_db.py`：FTS5 索引和搜索的单元测试

## Capabilities

### New Capabilities

- `session-fts`: 对话全文搜索 — SQLite FTS5 虚拟表索引 user/assistant 消息文本，支持 BM25 全文匹配，搜索结果与 MemoryStore 合并展示

### Modified Capabilities

<!-- None — existing spec requirements unchanged -->

## Impact

- 新依赖：无（sqlite3 是 Python 标准库）
- 数据文件：新增 `workspace/.sessions/sessions.db`（SQLite 数据库文件，gitignored）
- 性能：每次 `save_turn()` 增加一次 INSERT 操作（同步，~1ms）
- 向后兼容：`hybrid_search()` 签名不变；`/search` 命令行为增强但命令不变
