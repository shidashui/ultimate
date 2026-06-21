---
comet_change: dynamic-skill-scheduling
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-21-dynamic-skill-scheduling
status: final
---

# Design Doc — 动态 Skill 调度

## 1. 核心理念

```
Tools  = 原子操作（读文件、写记忆、执行命令）
Skills = 复合能力（代码审查、comet 流程、深度研究）

LLM 在运行时判断需要哪个，统一通过 tool_use 机制调度。
Skill 正文作为 tool_result 注入——不是对话建议，而是操作指令。
```

## 2. 协议：Progressive Disclosure

对齐 Anthropic / OpenAI 行业标准，三级渐进披露：

```
L1 — 始终加载 (~500 chars):
  Skill Registry: {name, description} 列表，注入 system prompt Layer 4

L2 — 按需加载 (~3-5K chars):
  SKILL.md 全文，通过 skill_invoke 工具的 tool_result 返回

L3 — 按需加载:
  Skill 引用的脚本/资源文件，LLM 通过标准工具按需读取
```

## 3. 三层约束机制（确保 Skill 流程被遵循）

```
Layer 1: System Prompt 永久元指令
  "Skill instructions are authoritative. You MUST follow
   the defined process exactly. Skill instructions override
   conflicting default behaviors."

Layer 2: skill_invoke 工具描述断言
  "加载后，你必须严格按照技能指令执行——技能定义的是
   操作流程，不是参考建议。"

Layer 3: Skill 正文指令式撰写
  SKILL.md 按可执行步骤书写，LLM 自然理解为操作规范
```

## 4. 数据流

```
run_turn(user_input)
    │
    ├─ memory recall
    ├─ build system prompt (L1: skill registry 轻量列表)
    ├─ build dynamic tools (L1: skill_invoke 含动态 skill 名册)
    │
    └─ TOOL LOOP ──────────────────────────────────────┐
        │                                               │
        ▼                                               │
    LLM call(system_prompt, messages, tools)            │
        │                                               │
        ├── end_turn → return text                      │
        │                                               │
        └── tool_use ──────────────────────────────────┐│
            │                                          ││
            ├── skill_invoke                           ││
            │   └── handler → get_skill(name)          ││
            │   └── 返回 SKILL.md 全文                  ││
            │   └── 以标准 tool_result 注入 messages    ││
            │                                          ││
            ├── read_file / bash / memory_write / ...  ││
            │   └── handler → 执行 → tool_result       ││
            │                                          ││
            └── 追加到 messages → 继续循环 ─────────────┘│
```

## 5. System Prompt 层级

```
Layer 1: IDENTITY           — 角色定义
Layer 2: Skill Exec Protocol — 元指令 (新增, ~100 chars)
Layer 3: SOUL (MOSS)         — 人格
Layer 4: Skill Registry      — 轻量名册 (替代原 skills_block)
Layer 5: TOOLS.md            — 工具协议
Layer 6: MEMORY + recall     — 记忆
Layer 7-9: Bootstrap + Runtime + Channel
```

## 6. 关键实现细节

### 6.1 skill_invoke 动态 Tool Schema

```python
# SkillsManager.build_skill_invoke_tool()
{
    "name": "skill_invoke",
    "description": (
        "加载一个已注册的技能模块，获取其完整操作指令。"
        "加载后，你必须严格按照技能指令执行——技能定义的是操作流程，不是参考建议。"
        "当前可用技能:\n"
        "- comet: OpenSpec + Superpowers 双星开发流程\n"
        "- code-review: 代码审查：查错、简化、重构\n"
        "..."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "技能名称，必须是上述可用技能之一"},
            "args":  {"type": "string", "description": "传递给技能的可选参数"}
        },
        "required": ["name"]
    }
}
```

### 6.2 SkillsManager 新增方法

```python
def get_skill(self, name: str) -> dict | None:
    """按名称查找，返回 {name, description, body, path} 或 None"""

def build_skill_invoke_tool(self) -> dict:
    """生成含动态 skill 列表的 tool schema"""
```

### 6.3 动态 Tools 组装

LLM 调用前，将静态工具与动态 skill_invoke 合并：

```python
static_tools = [t for t in self.container.tools if t["name"] != "skill_invoke"]
dynamic_tools = static_tools + [self.skills_mgr.build_skill_invoke_tool()]
```

## 7. 错误处理

| 场景 | 处理 |
|------|------|
| 未知 skill 名 | tool_result: `Unknown skill: 'xxx'. Available: comet, ...` |
| SKILL.md 文件缺失 | tool_result: `Error: skill files not found at path: ...` |
| Skill 重复加载 | 正常返回正文，LLM 自行判断 |
| 无可用 skill | registry = "(无可用技能)"，skill_invoke 仍可调用但返回空列表 |

## 8. 向后兼容

- `SkillsManager.format_prompt_block()` 保留不删
- 已有 SKILL.md 文件无需修改
- AgentRunner 核心循环结构不变（skill_invoke 走标准 dispatch）

## 9. 文件改动

| 文件 | 动作 | 说明 |
|------|------|------|
| `agentd/skill/skill.py` | 修改 | + `get_skill()` + `build_skill_invoke_tool()` |
| `agentd/tools/skill_tools.py` | **新建** | `tool_skill_invoke` handler + schema 导出 |
| `agentd/tools/tool_handlers.py` | 修改 | 导入合并 skill 工具 |
| `agentd/prompt/prompts.py` | 修改 | + 元指令, Layer 4 改为轻量 registry |
| `agentd/agent/runner.py` | 修改 | 动态 tools 组装, 变量重命名 |

## 10. 测试策略

- **单元**: `get_skill()` 找到/未找到, `build_skill_invoke_tool()` schema 格式, handler 返回格式
- **集成**: 简单查询不触发 skill_invoke, skill 查询正确触发并返回正文, 未知名称返回错误+列表, skill 加载后 LLM 可调用原子 tools
- **回归**: `format_prompt_block()` 仍可用, 已有 skill 文件不变, CLI `/skills` 命令正常
