## Tasks

- [x] 1. 创建 `agentd/session/session_db.py` — SessionDB 类（FTS5 表创建 + index_turn + search）
- [x] 2. 修改 `agentd/context/session.py` — SessionStore.save_turn() 调用 SessionDB.index_turn()
- [x] 3. 修改 `agentd/memory/memory.py` — hybrid_search() 合并 SessionDB 结果
- [x] 4. 修改 `cli/cli.py` — /search 展示合并搜索结果
- [x] 5. 创建 `tests/test_session_db.py` — FTS5 索引和搜索测试
- [x] 6. 运行全部测试，验证端到端
