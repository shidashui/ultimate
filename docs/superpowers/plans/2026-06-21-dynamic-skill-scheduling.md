---
change: dynamic-skill-scheduling
design-doc: docs/superpowers/specs/2026-06-21-dynamic-skill-scheduling-design.md
base-ref: none (no git repository)
archived-with: 2026-06-21-dynamic-skill-scheduling
---

# Implementation Plan — 动态 Skill 调度

## 执行顺序

Task 1 → Task 5 顺序执行，每步完成后提交，Task 6 为验证。

## Task 1: 扩展 SkillsManager

**文件**: `agentd/skill/skill.py`
**改动**: ~40 行新增

1. 新增 `get_skill(self, name: str) -> dict | None`
   - 遍历 `self.skills`，按 `name` 匹配
   - 找到返回完整 dict: `{name, description, invocation, body, path}`
   - 未找到返回 `None`

2. 新增 `build_skill_invoke_tool(self) -> dict`
   - 遍历 `self.skills`，构建 skill 名册字符串
   - 无 skill 时: `(无可用技能)`
   - 返回 Anthropic API tool schema dict，description 含动态 skill 列表

3. 保留 `format_prompt_block()` 不动

**验证**: 导入 SkillsManager，调 `get_skill("comet")` 返回非空；`build_skill_invoke_tool()` 返回合法 schema

## Task 2: 创建 skill_tools.py

**文件**: `agentd/tools/skill_tools.py`（新建）
**改动**: ~60 行

1. 实现 `tool_skill_invoke(name: str, args: str = "") -> str`
   - 从 `container.get("skills_mgr")` 获取 SkillsManager
   - 调 `get_skill(name)`
   - 找到 → 返回 `skill["body"]`
   - 未找到 → 返回 `Unknown skill: '{name}'. Available: comet, ...`

2. 定义 `skill_invoke` tool schema（静态基础版，不含动态 skill 列表）

3. 导出 `TOOLS` 和 `TOOL_HANDLERS`

**验证**: handler 被 tool_handlers.py 正确导入，未知 skill 返回错误+列表

## Task 3: 汇总注册

**文件**: `agentd/tools/tool_handlers.py`
**改动**: ~4 行

1. 在 `get_tools()` 中导入并合并 `SKILL_TOOLS`
2. 在 `get_tool_handlers()` 中导入并合并 `SKILL_TOOL_HANDLERS`

**验证**: `container.tools` 包含 `skill_invoke`，`container.tools_handlers` 含对应 handler

## Task 4: 切换 prompt Layer 4

**文件**: `agentd/prompt/prompts.py`
**改动**: ~5 行

1. 新增 Skill Execution Protocol 元指令（~100 chars），注入 Layer 1 身份后
2. `skills_block` 参数 → `skill_registry` 参数
3. Layer 4 从 `skills_block`（完整正文）改为 `skill_registry`（轻量注册表）
4. `Skill Instructions` 区块（memory 后的 `memory_write` 说明）保留

**验证**: `build_system_prompt(mode="full")` 输出不含 skill 正文，含 registry + 元指令

## Task 5: 更新 AgentRunner

**文件**: `agentd/agent/runner.py`
**改动**: ~10 行

1. `__init__`: `self.skills_block` → `self.skill_registry = self.skills_mgr.format_skill_registry()`
2. `run_turn()` / `async_run_turn()`:
   - `build_system_prompt()` 调用中 `skills_block=` → `skill_registry=`
   - LLM 调用前动态组装 tools:
     ```python
     static = [t for t in self.container.tools if t["name"] != "skill_invoke"]
     dynamic = static + [self.skills_mgr.build_skill_invoke_tool()]
     ```
   - 传入 `guard.guard_api_call(..., tools=dynamic)`
3. `process_tool_call()` 不变（`skill_invoke` handler 已在 container 中）

**验证**: `run_turn("你好")` 正常返回，tools 列表含动态 skill_invoke

## Task 6: 功能验证

无自动化测试框架，手动验证：

1. 启动 `python ultimate.py chat`
2. "你好" → 正常回复，不触发 skill_invoke
3. "帮我审查一下 agentd/agent/runner.py" → 触发 skill_invoke("code-review")
4. `/prompt` 确认 prompt 不含 skill 正文
5. `/skills` 确认 skill 名册仍在
