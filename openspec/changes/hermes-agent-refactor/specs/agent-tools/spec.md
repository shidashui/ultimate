# Agent Tools — Delta: 声明式工具注册

## 变更说明

工具注册机制从硬编码 import + 手动合并改为声明式 `ToolRegistry`。此变更修改 `agent-tools` spec 中关于工具注册和发现的部分。

## 修改的要求

### AT-REGISTRY: 声明式工具注册 (新增)

工具通过 `ToolRegistry.register()` 声明式注册，替代手动构造 schema 字典和手动合并 TOOLS 列表。

- **AT-REG-1**: 系统提供全局 `ToolRegistry` 单例 (`agentd.tools.registry.registry`)
- **AT-REG-2**: `registry.register(name, description, parameters, handler, toolset)` 接受工具定义并自动生成 Anthropic API 兼容的 tool schema
- **AT-REG-3**: 工具按 `toolset` 分类（`file`, `memory`, `skill`, `browser`, `general`）
- **AT-REG-4**: `registry.get_tools(enabled_toolsets=None)` 返回工具列表，可按 toolset 过滤
- **AT-REG-5**: `registry.get_handlers()` 返回 `{name: handler}` 映射
- **AT-REG-6**: 同名工具注册时打印 warning，后注册覆盖先注册
- **AT-REG-7**: 支持 `check_fn` 参数：返回 `False` 时工具静默跳过（条件可用性）

### AT-IMPORT: 工具自动发现 (修改)

工具文件的导入即触发注册（利用 Python 模块加载副作用）。

- **AT-IMP-1**: `tool_handlers.py` 通过 import 语句触发各工具模块加载和注册
- **AT-IMP-2**: 新增工具只需创建 `xxx_tools.py` 并在 `tool_handlers.py` 中 import，无需手动合并 TOOLS 列表
- **AT-IMP-3**: 向后兼容：保留模块级 `TOOLS` 和 `TOOL_HANDLERS` 导出变量

### AT-SKILL-STATIC: skill_invoke 静态 schema (修改)

`skill_invoke` 的工具描述不再动态拼接技能列表。

- **AT-SKILL-1**: `skill_invoke` 工具的 `description` 字段为静态文本，不包含技能名称列表
- **AT-SKILL-2**: 技能名称列表仅在 system prompt Layer 4 的 `skill_registry` 中展示
- **AT-SKILL-3**: 删除 `SkillsManager.build_skill_invoke_tool()` 方法

## 验收场景

1. **注册工具**: 通过 `registry.register()` 注册 → `registry.get_tools()` 返回对应 schema
2. **按 toolset 过滤**: `registry.get_tools(enabled_toolsets={"memory"})` 只返回 memory 工具
3. **同名覆盖 warning**: 注册同名工具 → 控制台输出 warning
4. **条件可用**: `check_fn=lambda: False` → 工具不被注册
5. **向后兼容**: `from agentd.tools.tool_handlers import TOOLS, TOOL_HANDLERS` 正常工作
