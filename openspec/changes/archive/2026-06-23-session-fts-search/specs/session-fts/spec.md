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
- **THEN** 返回空列表 `[]`，记忆搜索结果正常返回
