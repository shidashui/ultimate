# Tasks: CLI Skill Routing

- [x] **Task 1: 动态 Tab 补全**
  - `WordCompleter` 从 `skills_mgr.skills` 的 `invocation` 字段读取技能名
  - 保持硬编码命令和动态技能名合并
  - 无需刷新机制（启动时已有）

- [x] **Task 2: 技能路由**
  - 在 `handle_repl_command` 末尾增加动态技能匹配
  - 命中后显示触发反馈（console.print）
  - Skill body 作为 system message 注入后调用 AI

- [x] **Task 3: /help 集成**
  - `/help` 输出末尾追加"可用技能"段
  - 从 `skills_mgr.skills` 动态生成行
