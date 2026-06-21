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
            "args": {"type": "string", "description": "可选参数"}
        },
        "required": ["name"]
    }
}
```

### 2. Skill 正文作为 tool_result 返回

handler 返回 SKILL.md 的完整正文。LLM 在下一轮对话中看到这个 tool_result，按 skill 指令行事。不需要重建 system prompt。

```
Turn N:   LLM → tool_use: skill_invoke("comet")
Turn N+1: LLM 收到 tool_result: "# Comet — OpenSpec + Superpowers..."
          LLM 按 comet 指令行事 → end_turn 或继续调原子工具
```

### 3. Prompt 只保留轻量注册表

`format_skill_registry()` 替代 `format_prompt_block()`：

```
## Available Skills

向模型声明可用的技能模块。每个技能可通过 `skill_invoke` 工具按需加载。

| 技能 | 描述 |
|------|------|
| comet | OpenSpec + Superpowers 双星开发流程 |
| code-review | 代码审查：查错、简化、重构 |
| deep-research | 多源深度研究报告生成 |
| ... | ... |

需要某个技能的完整指令时，调用 skill_invoke 加载。
```

### 4. Skill 可链式调用原子工具

Skill 正文加载到上下文后，LLM 拥有了该领域的完整操作指令。Skill 指令可能引导 LLM 调用原子 tools 完成任务。

```
skill_invoke("code-review")
  → SKILL.md 正文: "审查代码时，先用 read_file 读取目标文件..."
  → LLM: tool_use: read_file("src/app.py")
  → LLM: tool_use: read_file("src/utils.py")
  → LLM: end_turn (输出审查报告)
```

### 5. SkillsManager 扩展

新增两个方法，保留所有现有方法：

```python
def get_skill(self, name: str) -> dict | None:
    """按名称查找 skill，返回完整信息（含 body）"""

def format_skill_registry(self) -> str:
    """生成轻量技能注册表（仅名称+描述，用于 prompt 注入）"""
```

## 文件改动详情

| 文件 | 动作 | 说明 |
|------|------|------|
| `agentd/skill/skill.py` | 修改 | 新增 `get_skill()`、`format_skill_registry()` |
| `agentd/tools/skill_tools.py` | **新增** | `skill_invoke` 工具定义 + handler |
| `agentd/tools/tool_handlers.py` | 修改 | 导入汇总 skill 工具 |
| `agentd/prompt/prompts.py` | 修改 | Layer 4 切换为轻量 registry |
| `agentd/agent/runner.py` | 不改 | skill 走标准 tool dispatch |

## 收益估算

```
场景: "你好"
  当前: prompt(~15K) + skills_block(~15K) + tools_schema(~3K) = ~33K chars
  优化: prompt(~15K) + registry(~0.5K) + tools_schema(~3K) = ~18.5K chars
  节省: ~44%

场景: "帮我做代码审查"
  当前: prompt + skills_block + tools = ~33K chars
  优化: prompt(~15K) + registry(~0.5K) + tools(~3K) [第一轮]
       + skill_body(~3K) [第二轮，按需]
       = ~21.5K chars
  节省: ~35%

场景: "帮我打开一个 comet change"（需多个 skill 链式）
  当前: prompt + skills_block + tools = ~33K chars
  优化: 按需加载所需 skill，不加载未使用的
       每多一个 skill 才多一次 skill_invoke 往返
```

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 多一次 skill_invoke 往返增加延迟 | Skill 正文通常 3-5K chars，一次 tool_use 往返 ~1-2s，换取 ~40% token 节省 |
| LLM 不知道 skill 存在而不调用 | registry 提供名称+描述，足够 LLM 判断是否需要 |
| LLM 过度调用 skill_invoke | 描述中注明 "仅在需要该领域的完整操作指令时调用" |
| `format_prompt_block()` 移除影响现有依赖 | 保留方法但不注入 prompt，可手动调用 |
