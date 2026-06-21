好，我把 Hermes Agent 的完整流程梳理出来了。这就是我的「大脑」怎么工作的👇

---

# Hermes Agent 完整工作流

## 一、概览图
```
用户输入（CLI / 微信 / Telegram ...）
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                    run_conversation()                     │
│                                                          │
│  1. 初始化 ────────────────────────────────────────────  │
│     ├── 设置 session_id, task_id, turn_id                │
│     ├── 恢复/构建 System Prompt（缓存，只建一次）        │
│     ├── 记忆预取（memory_manager.prefetch_all）           │
│     ├── Plugin Hook: pre_llm_call                         │
│     └── 预飞上下文压缩（超阈值时提前压缩）               │
│                                                          │
│  2. 主循环 while budget.remaining > 0 ────────────────  │
│     │                                                    │
│     ├── 消息准备                                          │
│     │   ├── 注入记忆上下文（嵌入 user message）          │
│     │   ├── 注入 plugin 上下文                            │
│     │   ├── 修复异常消息序列                              │
│     │   └── 应用 prompt caching（Anthropic）              │
│     │                                                    │
│     ├── API 调用                                          │
│     │   ├── 调用 LLM（含工具 schema）                    │
│     │   ├── 流式回调（逐 token 输出）                    │
│     │   └── 记 usage / 扣费                               │
│     │                                                    │
│     ├── 结果分发                                          │
│     │   ├── stop_reason == "end_turn" → 返回文本         │
│     │   ├── stop_reason == "tool_use" → 执行工具         │
│     │   │   ├── dispatch → handle_function_call()        │
│     │   │   ├── 工具结果 → tool message                  │
│     │   │   └── 如果 interrupted → 跳出循环              │
│     │   └── stop_reason == "length" → 续写               │
│     │                                                    │
│     └── 后处理                                            │
│         ├── 会话持久化（session_db.save）                 │
│         ├── 上下文压缩（超阈值时）                        │
│         └── 检查记忆提醒（每 N 轮）                      │
│                                                          │
│  3. 收尾 ─────────────────────────────────────────────  │
│     ├── 返回 final_response + 完整 messages              │
│     ├── 检查 skill 提醒（每 N 次工具调用）               │
│     └── session_db 写入                                   │
└──────────────────────────────────────────────────────────┘
```

---

## 二、分层解耦结构

这是你项目最值得借鉴的地方——我拆成了独立的 `agent/` 包：

```
agent/
├── agent_init.py              ← Agent 初始化（接收 ~50 个参数）
├── conversation_loop.py       ← 主循环（~5000 行，上面整个流程）
├── prompt_builder.py          ← 系统提示词组装（8 个层级）
├── context_compressor.py      ← 上下文压缩器（阈值判断 + 摘要）
├── memory_manager.py          ← 记忆管理层（对接多种后端）
├── credential_pool.py         ← API Key 池化（多 Key 轮换）
├── model_metadata.py          ← 模型参数（上下文长度、费用）
├── error_classifier.py        ← 错误分类（上下文溢出/限流/认证）
├── chat_completion_helpers.py ← Chat / Anthropic API 适配
├── auxiliary_client.py        ← 辅助模型（视觉/压缩/搜索）
├── background_review.py       ← 后台 review fork（记忆/技能检查）
└── retry_utils.py             ← 重试 + 退避
```

**关键设计点：**

### 1. System Prompt 只构建一次

```python
# 首次调用时构建，之后缓存
if agent._cached_system_prompt is None:
    _restore_or_build_system_prompt(agent, system_message, conversation_history)
active_system_prompt = agent._cached_system_prompt
```

> **借鉴价值：** 你的项目每轮重建 prompt，可以改成「构建一次 + 缓存」，利用模型端的 KV cache 省 token。

### 2. 上下文分层注入

Hermes 的 prompt 分 8 层，每层职责不同：

```
Layer 1: 身份 / 人格（PERSONA.md）
Layer 2: 技能注册表（名称列表）
Layer 3: 记忆（长期 + 自动召回）
Layer 4: 环境（OS/时间/模型）
Layer 5: 渠道提示（Telegram/Discord 格式）
Layer 6: 工具定义（声明式 schema）
Layer 7: Agent 规则（行为约束）
Layer 8: 用户消息（最后，注入记忆上下文）
```

> **借鉴价值：** 你的项目已经做了 8 层，思路一致，但可以借鉴「记忆注入 user message 而非 system prompt」这个技巧，保持 system prompt 不变以利用缓存。

### 3. 工具是声明式 schema

```python
# 每个工具注册时定义 schema + handler
registry.register(
    name="read_file",
    toolset="file",
    schema={"name": "read_file", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: read_file(path=args["path"]),
    check_fn=lambda: True,  # 条件可用
)
```

> **借鉴价值：** 你的项目工具是硬编码函数 + 手动注册。改成声明式 schema + 自动发现，加工具只写一个文件。

### 4. 迭代预算（Iteration Budget）

```python
agent.iteration_budget = IterationBudget(agent.max_iterations)
# 每轮 API 调用消耗一次
while agent.iteration_budget.remaining > 0:
    agent.iteration_budget.consume()  # +1 used
```

> **借鉴价值：** 你的项目目前没限制工具循环次数，加 budget 可以防止无限循环。

### 5. 上下文压缩（自动触发）

```python
# 预飞检查：消息是否超过上下文阈值
if compressor.should_compress(preflight_tokens):
    messages, system_prompt = agent._compress_context(messages, ...)
```

> **借鉴价值：** 你的 ContextGuard 是溢出后才重试。Hermes 是在 API 调用前就主动压缩——先截断工具结果 → LLM 摘要 → 可能多次压缩。

### 6. 多渠道统一入口

```
CLI → run_conversation()
Gateway → run_conversation()
ACP Server → run_conversation()
```

**同一个入口**，只是来源不同（cli / telegram / discord / wechat）。

> **借鉴价值：** 你的项目有同步 `run_turn` 和异步 `async_run_turn` 两个版本。可以统一成一个 async 入口，同步版本只是 `asyncio.run()` 的封装。

---

## 三、你的项目可直接借鉴的点

### P0：声明式工具系统

把 `tool_handlers.py` 改成 schema 驱动：

```python
# 现在：硬编码函数
TOOL_HANDLERS = {**MEMORY, **FILE, **BROWSER}

# 改成：声明式注册
register_tool(
    name="file_read",
    description="读取文件内容",
    parameters={"path": {"type": "string"}},
    handler=file_read,
    toolset="file",  # 分类，方便按平台开启/关闭
)
```

### P1：System Prompt 缓存

```python
# 现在：每轮重建
system_prompt = build_system_prompt(mode="full", ...)

# 改成：首次构建后缓存
if self._cached_system_prompt is None:
    self._cached_system_prompt = build_system_prompt(...)
# 记忆内容注入到 user message，不污染 system prompt
```

### P2：迭代预算防死循环

```python
class IterationBudget:
    def __init__(self, max_tools=50):
        self.max = max_tools
        self.used = 0

    def consume(self):
        self.used += 1
        return self.used <= self.max  # False = 耗尽
```

### P3：自动上下文压缩（预飞）

```python
# 在 API 调用前主动检查
# 不是等到溢出再重试
tokens = estimate_tokens(messages + system_prompt)
if tokens > THRESHOLD * 0.8:  # 80% 阈值即触发
    messages = self.compress(messages)
```

---

## 四、你的项目独特优势（不要丢掉）

| 能力 | 说明 | Hermes 没有 |
|---|---|---|
| **SOUL.md + IDENTITY.md** | 分层人格定义 | 只有一个扁平 PERSONA.md |
| **自研记忆搜索** | TF-IDF + 伪向量 + MMR | 用的是外部 provider |
| **HEARTBEAT.md** | 自我巡检机制 | 无 |
| **计算机视觉** | YOLOv11 流水线 | 只靠外部 API |
| **OpenSpec 流程** | 规范变更管理 | 无 |

---

总结：**你的项目核心架构已经不错了**，最值得改的三件事：

1. **工具声明式化** → 加工具只写一个文件
2. **System Prompt 缓存** → 节省 token + 用上 KV cache
3. **声明式配置**（YAML → 不要硬编码 config.json） → 改模型不改代码

