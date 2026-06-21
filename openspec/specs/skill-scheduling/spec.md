# Skill Scheduling — Delta: skill_invoke 静态化

## 变更说明

`skill_invoke` 工具的描述注册从"每轮动态拼接"改为"静态注册一次"。此变更简化 skill-scheduling 的实现，删除 `build_skill_invoke_tool()` 的动态生成逻辑。

## 修改的要求

### SS-STATIC: skill_invoke 静态注册 (修改)

`skill_invoke` 作为普通工具注册到 ToolRegistry，不在每轮重建 schema。

- **SS-STATIC-1**: `skill_tools.py` 中使用 `registry.register()` 注册 `skill_invoke`，与其他工具一致
- **SS-STATIC-2**: `skill_invoke` 的 description 为静态文本："加载一个已注册的技能模块，获取其完整操作指令。可用技能列表见系统提示词。"
- **SS-STATIC-3**: `SkillsManager.build_skill_invoke_tool()` 方法删除
- **SS-STATIC-4**: AgentRunner 不再调用 `skills_mgr.build_skill_invoke_tool()` 进行动态 tools 组装
- **SS-STATIC-5**: system prompt Layer 4 的 `skill_registry` 表格仍然是技能名称的唯一权威来源

### SS-COMPAT: 向后兼容 (不变)

以下要求不受影响：
- Progressive Disclosure 三层模型（L1 registry / L2 on-demand / L3 resources）
- Skill Execution Protocol 元指令（Layer 1.5）
- `tool_skill_invoke()` handler 逻辑（按名查找、返回正文）
- `SkillsManager.get_skill()` 和 `format_skill_registry()` 方法

## 验收场景

1. **skill_invoke 注册**: CLI 启动时 `skill_invoke` 出现在工具列表中
2. **技能加载**: LLM 调用 `skill_invoke(name="comet")` → 返回对应 SKILL.md 正文
3. **未知技能**: 调用不存在的技能名 → 返回可用列表
4. **不动态重建**: AgentRunner 不再每轮调用 `build_skill_invoke_tool()`
