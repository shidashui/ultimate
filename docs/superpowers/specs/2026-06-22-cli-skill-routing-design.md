---
comet_change: cli-skill-routing
role: technical-design
canonical_spec: openspec
---

# CLI Skill Routing — 技术设计

## 背景

当前 REPL 中输入 `/技能名` 无法被 CLI 层识别，依赖 AI 从 system prompt 的 skill_registry 表中自行判断。需要增加 CLI 层的技能匹配、Tab 补全和帮助集成。

## 核心决策

### 不修改 run_turn() 接口

复用 Hermes 现有的两阶段 skill 调用链：
1. system prompt 含 skill_registry 表格（名称 + 描述）
2. AI 识别 skill 名后调用 `skill_invoke(name="...")` 工具拉取 body

CLI 层只需匹配 + 反馈，无需预注入 body。

### 路由优先级

硬编码命令优先于动态技能匹配，避免 skill 名与现有命令冲突时覆盖。

## 实现要点

### 1. 动态补全

- `WordCompleter` 初始化时从 `skills_mgr.skills[*].invocation` 读取所有技能调用名
- 与硬编码命令列表合并去重
- 无热刷新需求（`discover()` 在 `AgentRunner.__init__()` 前已完成）

### 2. 技能路由

- 在 `handle_repl_command` 末尾（所有硬编码 elif 之后、`return False` 之前）增加技能匹配
- 匹配方式：`cmd` 与 skill 的 `invocation` 字段全等比较
- 命中后显示"技能: <name>"提示 + 描述，然后 `return False` 落入 AI 调用

### 3. /help 集成

- `/help` 输出末尾追加"可用技能"段
- 从 `skills_mgr.skills` 动态生成，格式与 `/skills` 一致

## 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| 技能名与现有命令冲突 | 低 | 硬编码命令优先匹配 |
| skill body 过长 | 无 | 不预注入，由 AI 按需拉取 |
| skills_mgr 未初始化 | 无 | WordCompleter 在 init_run 之前已就绪 |

## 测试

- 启动后 Tab 补全包含技能名
- 键入 `/comet test` 看到路由反馈 + AI 正确响应
- `/help` 列出所有技能
