## Why

当前 Skills 系统采用**静态全量注入**模式：启动时将全部 skill 的完整正文（SKILL.md）拼入 system prompt Layer 4。每个 skill 动辄 3000-5000 chars，多个 skill 叠加后 system prompt 轻松突破 30K chars。

问题在于——**无论用户问什么，这些 skill 正文都会被携带**。"你好" 和 "帮我做代码审查" 的 prompt 开销完全一样。

Skills 应该和 Tools 对等：LLM 在运行时判断 "需不需要"，而不是启动时无条件吞下全部。把 skill 从 "静态文本" 变为 "可调度的运行时资源"，模型按需加载，不浪费 token。

## What Changes

- **Skill 工具化**：新增 `skill_invoke` 通用调度工具，注册到 Anthropic API tools 数组，与 `read_file`、`bash` 等原子工具并列
- **Prompt 精简**：`build_system_prompt()` Layer 4 从「全部 skill 正文」改为「skill 注册表」（仅名称 + 一句话描述，~500 chars）
- **按需加载**：LLM 调用 `skill_invoke("comet")` → handler 从 SkillsManager 取出 SKILL.md 全文 → 作为 tool_result 注入上下文 → LLM 继续处理
- **SkillsManager 扩展**：新增 `get_skill(name)` 按名查找、`format_skill_registry()` 生成轻量注册表

## Capabilities

### New Capabilities
- `skill-scheduling`: 运行时 skill 调度模型 — skill 从静态 prompt 文本变为 LLM 可按需调用的能力单元

### Modified Capabilities
- `agent-tools`: 工具体系新增 `skill_invoke` 通用调度器，工具定义与处理器注册扩展

## Impact

- **agentd/skill/skill.py**：新增 `get_skill()`、`format_skill_registry()`，保留现有方法
- **agentd/tools/skill_tools.py**（新增）：`skill_invoke` 工具定义 + handler
- **agentd/tools/tool_handlers.py**：汇总 skill 工具
- **agentd/prompt/prompts.py**：Layer 4 改为轻量 registry
- **agentd/agent/runner.py**：无结构性改动（skill 通过标准 tool dispatch 路径处理）
- **不影响**：gateway/、platforms/、cli/ 等上层调用方
- **不影响**：已有 skill 文件（SKILL.md 内容不变，只是加载时机变了）
