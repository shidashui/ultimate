# 任务清单 — 动态 Skill 调度

## 核心实现

- [x] **Task 1: 扩展 SkillsManager** — `agentd/skill/skill.py`
  - 新增 `get_skill(name: str) -> dict | None`：按名称查找 skill，返回完整 dict（name, description, body, path）
  - 新增 `format_skill_registry() -> str`：生成轻量注册表，仅名称 + 一句话描述，用于 prompt 注入
  - 保留 `format_prompt_block()` 方法不动（向后兼容）

- [x] **Task 2: 创建 skill_tools.py** — `agentd/tools/skill_tools.py`（新文件）
  - 实现 `tool_skill_invoke(name: str, args: str = "") -> str` handler
  - handler 从 container 获取 SkillsManager，调 `get_skill(name)`
  - 找到 → 返回 SKILL.md 完整正文作为 tool_result
  - 未找到 → 返回 `Error: Unknown skill '{name}'` + 可用 skill 列表
  - 定义 `skill_invoke` 的 Anthropic API tool schema
  - 导出 `TOOLS` 和 `TOOL_HANDLERS`

- [x] **Task 3: 汇总注册 skill 工具** — `agentd/tools/tool_handlers.py`
  - 在 `get_tools()` 和 `get_tool_handlers()` 中导入并合并 skill_tools
  - 确保 `skill_invoke` 出现在最终 TOOLS 数组和 TOOL_HANDLERS 字典中

- [x] **Task 4: 切换 prompt Layer 4** — `agentd/prompt/prompts.py`
  - 将 `build_system_prompt()` 中的 `skills_block` 参数改为 `skill_registry: str = ""`
  - Layer 4 从注入 `skills_block`（完整正文）改为注入 `skill_registry`（轻量注册表）
  - 更新 `AgentRunner` 的调用处：`self.skills_block` → `self.skill_registry`
  - 确保 `mode="minimal"` 时也不注入完整 skill 正文

- [x] **Task 5: 更新 AgentRunner 初始化** — `agentd/agent/runner.py`
  - `self.skills_block` → `self.skill_registry = self.skills_mgr.format_skill_registry()`
  - `build_system_prompt()` 调用中 `skills_block=` → `skill_registry=`
  - 确认 `skill_invoke` 走标准 `process_tool_call` dispatch，无需特殊处理

## 验证

- [x] **Task 6: 功能验证**
  - 确认 "你好" 类简单查询不触发 skill_invoke 调用
  - 确认 "帮我审查代码" 类查询正确触发 skill_invoke → 加载正文 → 继续处理
  - 确认 registry 中的 skill 名称与实际可加载的 skill 一致
  - 确认不存在的 skill 名称返回友好错误 + 可用列表
