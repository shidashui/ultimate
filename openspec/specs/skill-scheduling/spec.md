# Skill Scheduling — 运行时技能调度

## 定义

Skills 是 LLM 可在运行时按需加载的复合能力模块。采用 Progressive Disclosure（渐进披露）模式：L1 名册始终可见，L2 正文按需加载，L3 资源按需引取。

## 核心要求

### 1. Progressive Disclosure 三级模型

- **L1 — 始终加载**：Skill Registry（名称 + 一句话描述），注入 system prompt Layer 4
- **L2 — 按需加载**：SKILL.md 全文，通过 `skill_invoke` 工具返回为 tool_result
- **L3 — 按需引取**：Skill 引用的脚本/资源文件，LLM 通过标准工具按需读取

### 2. 三层约束机制（确保 Skill 流程被遵循）

- **Layer 1 — System Prompt 永久元指令**：声明 "Skill instructions are authoritative. You MUST follow the defined process exactly."
- **Layer 2 — skill_invoke Tool Description 断言**：声明 "加载后必须严格按照技能指令执行，技能定义的是操作流程，不是参考建议"
- **Layer 3 — Skill 正文指令式撰写**：SKILL.md 按可执行步骤书写，LLM 自然理解为操作规范

### 3. 调度模型

- Skill 作为标准 Anthropic API tool 注册：`skill_invoke`
- `skill_invoke` 的 tool description 动态包含当前可用 skill 列表
- LLM 通过 `tool_use` 调用 skill，与调用 `read_file`、`bash` 的机制完全一致
- Handler 返回 SKILL.md 完整正文作为 `tool_result`
- LLM 在后续 turn 中读取 skill 指令，按需调用原子 tools 完成复合任务

### 4. 动态 Tool Schema

- 每轮 LLM 调用前，静态 tools 与动态 `skill_invoke` schema 合并
- `SkillsManager.build_skill_invoke_tool()` 生成含当前 skill 名册的完整 tool schema
- `skill_invoke` 不在静态 `container.tools` 中，每次动态拼接

### 5. 错误处理

- 未知 skill 名：返回 `Unknown skill: 'xxx'. Available: comet, ...`
- SKILL.md 文件缺失：返回 `Error: skill files not found at path: ...`
- 无可用 skill：registry 显示 `(无可用技能)`
- Skill 重复加载：正常返回正文，LLM 自行判断

### 6. 向后兼容

- `SkillsManager.format_prompt_block()` 保留不动
- 已有 SKILL.md 文件无需任何修改
