# Design: CLI Skill Routing

## 架构决策

```
用户输入 /comet 美化cli
        │
        ▼
handle_repl_command()
        │
        ├─ 1. 先匹配硬编码命令 (/help, /list, ...) → 原有逻辑
        │
        └─ 2. 未匹配 → 动态匹配 skills_mgr.skills
              │
              ├─ 命中 "comet" (invocation="/comet")
              │   ├─ console.print("[技能] comet 触发")
              │   ├─ 将 skill body 注入 messages 作为系统上下文
              │   ├─ 调用 AI runner.run_turn(user_input, messages, ...)
              │   └─ return True
              │
              └─ 未命中 → return False → 普通 AI 对话
```

## 关键设计选择

### 1. 动态补全
- `WordCompleter` 改为从 `skills_mgr.skills` 读取 `invocation` 字段
- 硬编码命令列表和技能列表合并为一个 `get_completions()` 方法
- 每次 `discover()` 后自动刷新补全列表

### 2. 技能路由
- 在 `handle_repl_command` 末尾（硬编码命令之后）增加动态技能匹配
- 匹配方式：`cmd` 去掉前缀 `/` 后与 skill 的 `name` 字段比较，或用 `invocation` 字段比较
- 命中后：显示触发反馈 + 将 skill body 注入为 system message + 调用 AI

### 3. 上下文注入
- Skill body 作为 `{"role": "system", "content": skill_body}` 临时插入消息列表
- 用户原始输入（含 `/comet` 前缀）保留为 user message
- 注入的 system message 不持久化到 session

### 4. /help 集成
- 在 `/help` 输出末尾追加"可用技能"段，从 `skills_mgr.skills` 动态生成

## 技术风险

- **Skill body 过长**：截断到 MAX_TOTAL_CHARS 限制内，超长时只注入前 N 字符 + 提示
- **循环依赖**：`skills_mgr` 在 `init_run()` 之后才可用，补全列表需延迟初始化
