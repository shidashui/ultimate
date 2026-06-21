# Comet Design Handoff

- Change: dynamic-skill-scheduling
- Phase: design
- Mode: compact
- Context hash: 89123cb227ad111394f9463146273711cf102302face7b9bdd2db05d2b964683

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/dynamic-skill-scheduling/proposal.md

- Source: openspec/changes/dynamic-skill-scheduling/proposal.md
- Lines: 1-32
- SHA256: 2063d0d83ba77444144bac4a9f5f7ceec5f04635f766a6c607bab8814317b970

```md
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
```

## openspec/changes/dynamic-skill-scheduling/design.md

- Source: openspec/changes/dynamic-skill-scheduling/design.md
- Lines: 1-179
- SHA256: 5c85df6385781de8f5ef07eb2c9c555ae53a92588b32e29454b83da2732ae5af

[TRUNCATED]

```md
# Design — 动态 Skill 调度

## 核心理念

```
Tools  = 原子操作（读文件、写记忆、执行命令）
Skills = 复合能力（代码审查、comet 流程、深度研究）

LLM 在运行时判断需要哪个，统一通过 tool_use 机制调度。
```

## 架构对比

### Before（静态注入）

```
build_system_prompt()
  └── Layer 4: skills_block = format_prompt_block()
        └── 全部 skill 正文拼入 (~30K chars)
              ├── comet: 5000 chars
              ├── code-review: 3000 chars
              ├── deep-research: 4000 chars
              └── ... 更多

每次 LLM 调用 → 无论"你好"还是"做代码审查" → 相同开销
```

### After（运行时调度）

```
build_system_prompt()
  └── Layer 4: skill_registry = format_skill_registry()
        └── 仅名称 + 一句话描述 (~500 chars)
              ├── comet: "OpenSpec + Superpowers 双星开发流程"
              ├── code-review: "代码审查：查错、简化、重构"
              └── deep-research: "多源深度研究报告生成"

LLM 运行时:
  "你好" → end_turn（不调任何 skill）
  "审查我的代码" → tool_use: skill_invoke("code-review")
                      → handler 取 SKILL.md → tool_result
                      → LLM 持有 code-review 全部指令
                      → 继续处理（可能调 read_file, edit_file 等原子工具）
```

## 统一调度模型

```
                      ┌─────────────────────┐
                      │   LLM 运行时判断     │
                      │   stop_reason 分派   │
                      └──────────┬──────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
         end_turn           tool_use           tool_use
         直接回复           原子工具            技能调度
              │             read_file           skill_invoke
              │             memory_write        ("code-review")
              │             bash                     │
              │             ...                 ┌────┴────┐
              ▼                                 ▼         ▼
         返回文本                          加载正文   注入上下文  LLM继续
```

## 关键设计决策

### 1. Skill 作为标准 Tool 注册

`skill_invoke` 和其他 tool（read_file、bash）使用完全相同的 Anthropic API tool 机制。不需要特殊 dispatch 路径、不需要文本解析。

```python
# skill_invoke 的 tool schema
{
    "name": "skill_invoke",
    "description": "加载一个已注册的技能模块...",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "技能名称"},
```

Full source: openspec/changes/dynamic-skill-scheduling/design.md

## openspec/changes/dynamic-skill-scheduling/tasks.md

- Source: openspec/changes/dynamic-skill-scheduling/tasks.md
- Lines: 1-39
- SHA256: 6d92e77c84097212d481108621a7a403a434991ed282db832f59bfa85366bdac

```md
# 任务清单 — 动态 Skill 调度

## 核心实现

- [ ] **Task 1: 扩展 SkillsManager** — `agentd/skill/skill.py`
  - 新增 `get_skill(name: str) -> dict | None`：按名称查找 skill，返回完整 dict（name, description, body, path）
  - 新增 `format_skill_registry() -> str`：生成轻量注册表，仅名称 + 一句话描述，用于 prompt 注入
  - 保留 `format_prompt_block()` 方法不动（向后兼容）

- [ ] **Task 2: 创建 skill_tools.py** — `agentd/tools/skill_tools.py`（新文件）
  - 实现 `tool_skill_invoke(name: str, args: str = "") -> str` handler
  - handler 从 container 获取 SkillsManager，调 `get_skill(name)`
  - 找到 → 返回 SKILL.md 完整正文作为 tool_result
  - 未找到 → 返回 `Error: Unknown skill '{name}'` + 可用 skill 列表
  - 定义 `skill_invoke` 的 Anthropic API tool schema
  - 导出 `TOOLS` 和 `TOOL_HANDLERS`

- [ ] **Task 3: 汇总注册 skill 工具** — `agentd/tools/tool_handlers.py`
  - 在 `get_tools()` 和 `get_tool_handlers()` 中导入并合并 skill_tools
  - 确保 `skill_invoke` 出现在最终 TOOLS 数组和 TOOL_HANDLERS 字典中

- [ ] **Task 4: 切换 prompt Layer 4** — `agentd/prompt/prompts.py`
  - 将 `build_system_prompt()` 中的 `skills_block` 参数改为 `skill_registry: str = ""`
  - Layer 4 从注入 `skills_block`（完整正文）改为注入 `skill_registry`（轻量注册表）
  - 更新 `AgentRunner` 的调用处：`self.skills_block` → `self.skill_registry`
  - 确保 `mode="minimal"` 时也不注入完整 skill 正文

- [ ] **Task 5: 更新 AgentRunner 初始化** — `agentd/agent/runner.py`
  - `self.skills_block` → `self.skill_registry = self.skills_mgr.format_skill_registry()`
  - `build_system_prompt()` 调用中 `skills_block=` → `skill_registry=`
  - 确认 `skill_invoke` 走标准 `process_tool_call` dispatch，无需特殊处理

## 验证

- [ ] **Task 6: 功能验证**
  - 确认 "你好" 类简单查询不触发 skill_invoke 调用
  - 确认 "帮我审查代码" 类查询正确触发 skill_invoke → 加载正文 → 继续处理
  - 确认 registry 中的 skill 名称与实际可加载的 skill 一致
  - 确认不存在的 skill 名称返回友好错误 + 可用列表
```

## openspec/changes/dynamic-skill-scheduling/specs/agent-tools/spec.md

- Source: openspec/changes/dynamic-skill-scheduling/specs/agent-tools/spec.md
- Lines: 1-32
- SHA256: bc7e301ff7d0cc559e1d67d0e8434c759c609078d45939ae76f9ac63433a8462

```md
# Agent Tools — 系统资源调度协议

## 定义

可用工具集及其调用规范。以 MOSS 视角，工具是「系统可调度的外部资源」。Skills 同样通过工具机制按需调度。

## 核心要求

### 1. 工具分类

| 资源类型 | 工具 | 用途 |
|---------|------|------|
| **文件系统接口** | read_file / write_file / edit_file / list_directory | 工作区文件访问与修改 |
| **执行引擎** | bash / cmd | 命令行指令执行 |
| **记忆子系统** | memory_write / memory_search | 长期数据存储与检索 |
| **技能调度器** | skill_invoke | 按需加载复合能力模块（技能） |
| **情报采集** | Web Search / Web Fetch | 外部信息获取 |
| **时基系统** | get_current_time | 时间参考 |

### 2. 调用规范

- 每次工具调用前，确认调用参数最优——尽量减少调用次数
- 文件操作前，先读取确认当前状态，不假设文件内容
- 工具输出保持精确解析——关注执行结果而非过程冗长输出
- 执行失败时，返回错误码与关键状态信息，不添加无关描述
- `skill_invoke` 用于加载领域完整操作指令，不应重复调用同一 skill

### 3. 资源约束

- 工具产出需自行截断管理——上下文窗口有限
- 高开销操作（批量文件读写、大规模搜索）需评估后再执行
- 不执行超出系统安全边界（路径穿越防护等）的操作
```

## openspec/changes/dynamic-skill-scheduling/specs/skill-scheduling/spec.md

- Source: openspec/changes/dynamic-skill-scheduling/specs/skill-scheduling/spec.md
- Lines: 1-45
- SHA256: 7c51d05472ecdeb39562e40d0f76513cfa4635385e86ff49a982d175bf12909c

```md
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
```

