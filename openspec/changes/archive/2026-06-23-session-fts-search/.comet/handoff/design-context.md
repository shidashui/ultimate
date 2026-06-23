# Comet Design Handoff

- Change: session-fts-search
- Phase: design
- Mode: compact
- Context hash: c33079ea89fccc05cd419cce6e91b00e1e520ddabe2b8af924d8b5ec106673e2

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/session-fts-search/proposal.md

- Source: openspec/changes/session-fts-search/proposal.md
- Lines: 1-28
- SHA256: 1ca692aa9b132ab5167dcbe5bd6f713f00066f7298f01c460e86a6932b2ec57e

```md
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
```

## openspec/changes/session-fts-search/design.md

- Source: openspec/changes/session-fts-search/design.md
- Lines: 1-62
- SHA256: da0da592f9e092dc7ec1926a97d8a6471242fdbdd52f92da9f1d08a6c5d36d4c

```md
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
```

## openspec/changes/session-fts-search/tasks.md

- Source: openspec/changes/session-fts-search/tasks.md
- Lines: 1-8
- SHA256: b9bfb946c21f42349a28813521d12cc06b8cc549d98fdf0cb97f5300ab927bc4

```md
## Tasks

- [ ] 1. 创建 `agentd/session/session_db.py` — SessionDB 类（FTS5 表创建 + index_turn + search）
- [ ] 2. 修改 `agentd/context/session.py` — SessionStore.save_turn() 调用 SessionDB.index_turn()
- [ ] 3. 修改 `agentd/memory/memory.py` — hybrid_search() 合并 SessionDB 结果
- [ ] 4. 修改 `cli/cli.py` — /search 展示合并搜索结果
- [ ] 5. 创建 `tests/test_session_db.py` — FTS5 索引和搜索测试
- [ ] 6. 运行全部测试，验证端到端
```

## openspec/changes/session-fts-search/specs/session-fts/spec.md

- Source: openspec/changes/session-fts-search/specs/session-fts/spec.md
- Lines: 1-81
- SHA256: f349a6497085fbff9d896645316289610afe50991225c5d773dc143826c18f2a

[TRUNCATED]

```md
# session-fts

对话全文搜索能力 — SQLite FTS5 索引 user/assistant 消息文本。

## ADDED Requirements

### Requirement: FTS5 索引写入

SessionDB 必须在每次保存对话轮次时同步写入 FTS5 索引。

#### Scenario: 用户消息被索引

- **GIVEN** SessionDB 已初始化且 FTS5 表已创建
- **WHEN** 调用 `index_turn(session_id, "user", "今天天气怎么样", ts)`
- **THEN** 该消息内容可被 FTS5 全文搜索匹配

#### Scenario: assistant 消息被索引

- **GIVEN** SessionDB 已初始化
- **WHEN** 调用 `index_turn(session_id, "assistant", "今天天气晴朗", ts)`
- **THEN** 该消息内容可被 FTS5 全文搜索匹配

#### Scenario: tool_use 和 tool_result 不写入索引

- **GIVEN** SessionDB 已初始化
- **WHEN** SessionStore.save_turn 收到 role 为 "tool_use" 或 "tool_result" 的记录
- **THEN** SessionDB.index_turn 不被调用

### Requirement: FTS5 全文搜索

SessionDB.search() 必须支持 BM25 全文匹配，返回按相关度排序的结果。

#### Scenario: 精确匹配

- **GIVEN** FTS5 索引中有 "今天天气怎么样" 和 "明天会下雨吗" 两条记录
- **WHEN** 调用 `search("天气", limit=5)`
- **THEN** 返回结果包含 "今天天气怎么样"，且排在 "明天会下雨吗" 之前

#### Scenario: 无匹配结果

- **GIVEN** FTS5 索引中有若干记录
- **WHEN** 调用 `search("xyz不存在的关键词abc", limit=5)`
- **THEN** 返回空列表 `[]`

#### Scenario: limit 截断

- **GIVEN** FTS5 索引中有 10 条匹配记录
- **WHEN** 调用 `search("关键词", limit=3)`
- **THEN** 返回最多 3 条结果

### Requirement: 搜索结果合并

MemoryStore.hybrid_search() 必须合并 SessionDB 的搜索结果，并标注来源。

#### Scenario: 合并展示

- **GIVEN** MemoryStore 有记忆搜索结果，SessionDB 有对话搜索结果
- **WHEN** 调用 `hybrid_search("关键词")`
- **THEN** 返回结果包含 `source: "memory"` 和 `source: "session"` 两种来源的条目

#### Scenario: SessionDB 不可用时降级

- **GIVEN** SessionDB 数据库文件损坏或不存在
- **WHEN** 调用 `hybrid_search("关键词")`
- **THEN** 仍然返回 MemoryStore 的记忆搜索结果，不抛异常

### Requirement: 降级容错

SessionDB 操作失败时不得中断主流程。

#### Scenario: INSERT 失败不影响对话

- **GIVEN** SessionDB 的 INSERT 操作因磁盘满等原因失败
- **WHEN** SessionStore.save_turn() 调用 index_turn()
- **THEN** 对话正常保存到 JSONL，不抛异常，不中断对话流

#### Scenario: search 异常返回空结果

- **GIVEN** SessionDB 的 search() 因数据库锁等原因失败
- **WHEN** hybrid_search() 调用 SessionDB.search()
```

Full source: openspec/changes/session-fts-search/specs/session-fts/spec.md

