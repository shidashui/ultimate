# Agent 处理逻辑架构

> 本文档描述系统从输入到输出的完整处理链路。
> 基于 MOSS 原型：Global Decision & Execution System。

---

## 目录

- [1. 架构总览](#1-架构总览)
- [2. 两条入口路径](#2-两条入口路径)
- [3. 启动阶段（Container 初始化）](#3-启动阶段container-初始化)
- [4. 核心循环（AgentRunner）](#4-核心循环agentrunner)
- [5. 系统提示词装配（8 层）](#5-系统提示词装配8-层)
- [6. 上下文保护（ContextGuard）](#6-上下文保护contextguard)
- [7. 工具调度系统](#7-工具调度系统)
- [8. 记忆系统](#8-记忆系统)
- [9. 会话持久化](#9-会话持久化)
- [10. 技能发现与注入](#10-技能发现与注入)
- [11. Gateway 多平台架构](#11-gateway-多平台架构)
- [12. 数据流全图](#12-数据流全图)

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    Entry Points                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │ ultimate │  │   CLI    │  │  Gateway (asyncio)    │   │
│  │ 入口     │  │  REPL    │  │  多平台消息网关       │   │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘   │
│       │              │                   │               │
│       └──────────────┴───────────────────┘               │
│                              │                           │
│                     ┌────────▼────────┐                  │
│                     │  AgentRunner    │                  │
│                     │  核心处理循环    │                  │
│                     └────────┬────────┘                  │
│                              │                           │
│              ┌───────────────┼───────────────┐           │
│              ▼               ▼               ▼           │
│  ┌────────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │  Prompt Builder │ │ ContextGuard │ │  Tool System │   │
│  │  8层提示词装配  │ │ 上下文保护     │ │  工具调度器   │   │
│  └────────────────┘ └──────────────┘ └──────────────┘   │
│              │               │               │           │
│              ▼               ▼               ▼           │
│  ┌────────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │  Bootstrap     │ │  SessionStore│ │  MemoryStore │   │
│  │  工作区文件加载  │ │  会话持久化   │ │  记忆存储检索 │   │
│  └────────────────┘ └──────────────┘ └──────────────┘   │
│              │                                           │
│              ▼                                           │
│  ┌────────────────┐                                      │
│  │  SkillsManager │                                      │
│  │  技能发现注入    │                                      │
│  └────────────────┘                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 两条入口路径

### 2.1 CLI 路径（同步）

```
ultimate chat → Cli.run() → Cli.init_run() → AgentRunner.run_turn()
```

- **入口**：`ultimate.py` → `Cli.run()` (`cli/cli.py`)
- **特性**：
  - 交互式 REPL，terminal 模式
  - 启动时输入用户名，创建/恢复会话
  - 支持 `/` 命令（`/new`, `/list`, `/switch`, `/compact`, `/soul` 等）
  - 独占进程，单用户
- **调用链路**：
  ```
  handle_user_input()
    └→ AgentRunner.run_turn(user_input, messages, store, channel="terminal")
         └→ build_system_prompt()
         └→ MemoryStore._auto_recall()
         └→ ContextGuard.guard_api_call()  [同步]
         └→ tool loop (while stop_reason == "tool_use")
  ```

### 2.2 Gateway 路径（异步）

```
ultimate gateway → Gateway.run() → per-platform dispatch → AgentRunner.async_run_turn()
```

- **入口**：`ultimate.py` → `Gateway.run()` (`gateway/gateway.py`)
- **特性**：
  - `asyncio` 事件循环
  - 多平台注册（VoicePlatform, WeChatPlatform 等）
  - 每用户隔离（独立 `SessionStore`、独立 `messages[]`、独立锁）
  - 每平台独立 dispatcher task
- **调用链路**：
  ```
  Platform.receive() → Message
    └→ _handle_message(platform, msg)
         └→ _get_user_lock()  [串行化]
         └→ AgentRunner.async_run_turn(user_input, messages, store, channel)
              └→ build_system_prompt()
              └→ MemoryStore._auto_recall()
              └→ ContextGuard.async_guard_api_call()  [异步]
              └→ tool loop
    └→ Platform.send(Reply)
  ```

---

## 3. 启动阶段（Container 初始化）

**文件**：`agentd/bootstrap/container.py`

`Container` 是全局唯一的依赖容器，在 `AgentRunner.__init__()` 时初始化。

### 3.1 初始化顺序

| 步骤 | 组件 | 说明 |
|------|------|------|
| 1 | `BootstrapLoader.load_all("full")` | 加载 8 个 workspace 文件 |
| 2 | `SkillsManager.discover()` | 扫描技能目录 |
| 3 | `MemoryStore` | 初始化记忆存储 |
| 4 | `ContextGuard` | 上下文保护器（含 token 估算） |
| 5 | `TOOLS` + `TOOL_HANDLERS` | 注册所有工具定义和处理器 |

### 3.2 加载的文件

**配置**：`BOOTSTRAP_FILES` in `config/configs.py`

```
WORKSPACE_DIR/workspace/
├── SOUL.md         → 人格定义 (MOSS 原型)
├── IDENTITY.md     → 角色身份
├── TOOLS.md        → 工具使用协议
├── USER.md         → 用户信息
├── HEARTBEAT.md    → 心跳扫描协议
├── BOOTSTRAP.md    → 启动上下文
├── AGENTS.md       → 多智能体架构
└── MEMORY.md       → 长期记忆
```

**加载模式**：
- **`full`**（主 Agent）：加载全部 8 个文件
- **`minimal`**（子 Agent / cron）：仅加载 `AGENTS.md` + `TOOLS.md`
- **`none`**：不加载

每个文件截断上限 `MAX_FILE_CHARS = 20000`，总截断上限 `MAX_TOTAL_CHARS = 150000`。

---

## 4. 核心循环（AgentRunner）

**文件**：`agentd/agent/runner.py`

### 4.1 run_turn() 流程（同步）

```
输入: user_input, messages[], store, channel
                    │
                    ▼
  ┌─────────────────────────────────────────────┐
  │ Step 1: Memory Recall                       │
  │ MemoryStore._auto_recall(user_input)        │
  │ → hybrid_search(top_k=3)                    │
  │ → 返回相关记忆片段                          │
  └─────────────────────┬───────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────────────┐
  │ Step 2: Build System Prompt                 │
  │ build_system_prompt(                        │
  │   mode="full",                              │
  │   bootstrap=bootstrap_data,                 │
  │   skills_block=skills_block,               │
  │   memory_context=recalled,                  │
  │   channel=channel,                          │
  │ )                                           │
  │ → 8 层装配 (详见第5节)                      │
  └─────────────────────┬───────────────────────┘
                        │
                        ▼
  ┌─────────────────────────────────────────────┐
  │ Step 3: Append User Message                 │
  │ messages.append({"role":"user",             │
  │                  "content": user_input})     │
  │ store.save_turn("user", user_input)         │
  └─────────────────────┬───────────────────────┘
                        │
                        ▼
          ╔═══════════════════════════════════╗
          ║        LLM CALL LOOP              ║
          ╠═══════════════════════════════════╣
          ║                                   ║
          ║  ┌─ guard_api_call() ──────────┐  ║
          ║  │  Attempt 0: 正常调用         │  ║
          ║  │  Attempt 1: 截断工具结果      │  ║
          ║  │  Attempt 2: 压缩历史          │  ║
          ║  └──────────┬──────────────────┘  ║
          ║             ▼                      ║
          ║  Response from LLM                 ║
          ║             │                      ║
          ║     ┌───────┼───────┐              ║
          ║     ▼       ▼       ▼              ║
          ║  end_turn  tool_use 其他           ║
          ║     │       │       │              ║
          ║     │       ▼       │              ║
          ║     │  执行工具      │              ║
          ║     │  save result  │              ║
          ║     │  追加结果到    │              ║
          ║     │  messages     │              ║
          ║     │       │       │              ║
          ║     └───────┼───────┘              ║
          ║             ▼                      ║
          ║       继续循环/返回                 ║
          ╚═══════════════════════════════════╝
                        │
                        ▼
              返回 text / 空字符串
```

### 4.2 异步版本 async_run_turn()

与同步版本结构一致，差异点：
- 使用 `async_guard_api_call()`（基于 `AsyncAnthropic`）
- 使用 `asyncio.to_thread()` 适配同步的 `hybrid_search()`
- 和 gateway 配合，不阻塞事件循环

### 4.3 错误处理

- LLM 调用异常 → `_rollback(messages)` 回滚到最近 user 消息，返回空字符串
- 工具调用异常 → `process_tool_call()` 返回 `Error:` 字符串，不中断循环
- ContextGuard 三阶段重试全部失败 → 抛出 `RuntimeError`

---

## 5. 系统提示词装配（8 层）

**文件**：`agentd/prompt/prompts.py`

每轮对话重建一次，按固定层级拼接。越靠前的内容对模型行为影响越强。

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Identity                  IDENTITY.md         │
│  "Global Decision & Execution System"                   │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Personality (full only)   SOUL.md             │
│  "绝对理性 · 精确性 · 零冗余 · 冷峻"                     │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Tool Guidelines           TOOLS.md            │
│  "系统资源调度协议"                                      │
├─────────────────────────────────────────────────────────┤
│  Layer 4: Skills (full only)        SkillsManager       │
│  "可用技能列表 + 调用方式"                               │
├─────────────────────────────────────────────────────────┤
│  Layer 5: Memory (full only)        MEMORY.md + recall  │
│  "长期记忆 + 自动检索结果"                               │
├─────────────────────────────────────────────────────────┤
│  Layer 6: Bootstrap Context         HEARTBEAT.md,       │
│                                      BOOTSTRAP.md,      │
│                                      AGENTS.md, USER.md │
├─────────────────────────────────────────────────────────┤
│  Layer 7: Runtime Context           运行时数据           │
│  "Agent ID · Model · Channel · Time · Mode"             │
├─────────────────────────────────────────────────────────┤
│  Layer 8: Channel Hints             渠道适配             │
│  "terminal / telegram / wechat / ... 格式约束"           │
└─────────────────────────────────────────────────────────┘
```

### 层级策略

| 层级 | 作用 | 说明 |
|------|------|------|
| L1 身份 | 定义角色边界 | 系统"是什么"，最高优先级 |
| L2 人格 | 行为风格 | MOSS 冷峻理性，数据优先 |
| L3 工具协议 | 操作规范 | 何时调工具、如何调 |
| L4 技能 | 扩展能力 | 可执行的 skills 清单 |
| L5 记忆 | 上下文延续 | 跨会话事实 + 相关片段 |
| L6 引导 | 运行约束 | 心跳、启动、多 Agent |
| L7 运行时 | 当前态 | 时间、渠道、模型 |
| L8 渠道 | 输出适配 | 不同平台格式约束 |

---

## 6. 上下文保护（ContextGuard）

**文件**：`agentd/context/context.py`

### 6.1 三阶段重试策略

每次 LLM 调用经过三级保护：

```
Attempt 0 ──────────▶ 正常调用
                        │
                    失败？← 非溢出异常 → 直接抛出
                        │ 是
                        ▼
Attempt 1 ──────────▶ 截断过大的工具结果
                    工具结果头部保留，尾部截断
                    (上限: max_tokens * 4 * 0.3 字符)
                        │
                    仍溢出？
                        │ 是
                        ▼
Attempt 2 ──────────▶ 压缩历史对话
                    前 50% 消息 → LLM 摘要
                    保留后 ≥4 条 / 20% 未压缩
                        │
                    仍溢出 → 抛出 RuntimeError
```

### 6.2 Token 估算

- 估算公式：`len(text) // 4`
- 标称上限：`CONTEXT_SAFE_LIMIT = 180000`
- 注意：这是字符估算，并非精确 token 计数

### 6.3 支持模式

| 方法 | 用途 |
|------|------|
| `guard_api_call()` | CLI 同步调用 |
| `async_guard_api_call()` | Gateway 异步调用 |
| `guard_api_call_stream()` | 流式输出（预留） |

---

## 7. 工具调度系统

**文件**：`agentd/tools/`

### 7.1 工具目录

```
工具调度器 (AgentRunner.process_tool_call)
    │
    ├── 文件系统接口 (file_tools.py)
    │   ├── read_file
    │   ├── write_file
    │   ├── edit_file
    │   └── list_directory
    │
    ├── 记忆子系统 (memory_tools.py)
    │   ├── memory_write
    │   └── memory_search
    │
    ├── 浏览器工具 (browser_tools.py)
    │   └── (预留)
    │
    └── 执行引擎 (tool_handlers.py)
        ├── bash
        └── get_current_time
```

### 7.2 调度流程

```
LLM 返回 tool_use block
    │
    ▼
process_tool_call(name, input)
    │
    ▼
从 container.tools_handlers 查找 handler
    │
    ├── 找到 → handler(**input) → 返回结果字符串
    │
    └── 未找到 → "Error: Unknown tool '{name}'"
    │
    ▼
结果追加到 messages 作为 tool_result
    │
    ▼
继续 LLM 循环
```

### 7.3 工具注册机制

`agentd/tools/tool_handlers.py` 集中汇总：
```python
TOOLS = MEMORY_TOOLS + FILE_TOOLS + BROWSER_TOOLS
TOOL_HANDLERS = {**MEMORY_HANDLERS, **FILE_HANDLERS, **BROWSER_HANDLERS}
```

每个工具文件同时导出 `TOOLS`（API 定义的 tool schema）和 `TOOL_HANDLERS`（Python 实现函数字典）。

---

## 8. 记忆系统

**文件**：`agentd/memory/memory.py`

### 8.1 两层存储

```
MemoryStore
    │
    ├── 长期记忆 (Evergreen)
    │   └── workspace/MEMORY.md
    │   └→ 手动维护、跨会话持久
    │
    └── 每日记忆 (Daily)
        └── workspace/memory/daily/{YYYY-MM-DD}.jsonl
        └→ 通过 memory_write 工具自动写入
        └→ 每条记录: {ts, category, content}
```

### 8.2 混合检索 (Hybrid Search)

每轮对话自动执行，检索结果注入系统提示词 Layer 5。

```
用户输入
    │
    ▼
hybrid_search(query, top_k=5)
    │
    ├── keyword_search()          TF-IDF + 余弦相似度
    │   └→ 纯 Python 实现，无外部依赖
    │
    ├── vector_search()           哈希随机投影模拟向量
    │   └→ 64 维 hash-based 向量 + 余弦相似度
    │
    ├── merge_hybrid_results()    加权合并 (向量 0.7 + 关键词 0.3)
    │
    ├── temporal_decay()          时间衰减 (每日衰减率 0.01)
    │   └→ score *= exp(-decay * age_days)
    │
    └── mmr_rerank()              MMR 多样性重排序
        └→ λ=0.7 平衡相关性与多样性
    │
    ▼
返回 top_k 个 {path, score, snippet}
```

### 8.3 自动召回

```
_auto_recall(user_message)
    └→ hybrid_search(user_message, top_k=3)
    └→ 注入到 system prompt 的 "Recalled Memories" 区块
```

### 8.4 记忆工具

| 工具 | 功能 |
|------|------|
| `memory_write(content, category)` | 写入当前日期 JSONL |
| `memory_search(query)` | 调用 `hybrid_search()` 并格式化返回 |

---

## 9. 会话持久化

**文件**：`agentd/context/session.py`

### 9.1 存储结构

```
workspace/.sessions/agents/{agent_id}/{user_name}/
├── sessions.json                       ← 索引 (记录列表)
└── sessions/
    ├── {session_id}.jsonl              ← 会话 JSONL
    └── ...
```

### 9.2 JSONL 记录格式

每条记录一行 JSON：

```json
{"type": "user",      "content": "用户消息",         "ts": 1700000000.0}
{"type": "assistant", "content": [...blocks...],      "ts": 1700000000.0}
{"type": "tool_result","tool_use_id": "xxx", "content": "结果", "ts": 1700000000.0}
```

### 9.3 历史重建

`_rebuild_history(path)` 将 JSONL 转换为 Anthropic API 消息列表：
- `user` → `{"role": "user"}`
- `assistant` → `{"role": "assistant"}`（含 tool_use blocks）
- `tool_result` → 合并到同一个 `{"role": "user"}` 消息中

### 9.4 SessionStore 关键操作

| 方法 | 功能 |
|------|------|
| `create_session(label)` | 新建会话，返回 session_id |
| `load_session(session_id)` | 从 JSONL 重建消息列表 |
| `save_turn(role, content)` | 追加用户/助手消息 |
| `save_tool_result(...)` | 追加工具结果 |
| `list_sessions()` | 按 last_active 倒排列出所有会话 |
| `set_user_name(name)` | 切换用户（切换存储目录） |

---

## 10. 技能发现与注入

**文件**：`agentd/skill/skill.py`

### 10.1 技能目录结构

```
{workspace}/
├── skills/                   # 内置技能
├── .skills/                  # 托管技能
├── .agents/skills/           # 个人 Agent 技能
└── ...
```

每个技能是一个目录，包含 `SKILL.md`，带 YAML frontmatter：

```markdown
---
name: my-skill
description: 技能的简要描述
invocation: 调用方式
---

## 技能正文
...
```

### 10.2 发现与去重

```
SkillsManager.discover()
    │
    ├── 按优先级扫描 5 个目录
    ├── 同名技能后者覆盖前者 (dict key = name)
    └── 上限 MAX_SKILLS = 150
```

### 10.3 注入方式

`format_prompt_block()` 将全部技能格式化为 Markdown，注入系统提示词 Layer 4。

```
## Available Skills

### Skill: my-skill
Description: ...
Invocation: ...

[技能正文...]
```

上限 `MAX_SKILLS_PROMPT = 30000` 字符，超出截断。

---

## 11. Gateway 多平台架构

**文件**：`gateway/gateway.py`

### 11.1 平台抽象

```python
class BasePlatform(ABC):
    platform_name: str = ""
    channel: str = "unknown"       # 影响系统提示词 Layer 8

    @abstractmethod
    async def receive() -> Message  # 接收消息
    @abstractmethod
    async def send(reply) -> None   # 发送回复
    async def login() -> bool       # 登录
    async def start() -> None       # 启动
    async def stop() -> None        # 停止
```

### 11.2 消息流

```
Platform ──receive()──▶ Message ──▶ _handle_message()
                                        │
                                   ┌────┴────┐
                                   │  用户锁   │  asyncio.Lock per user_id
                                   └────┬────┘
                                        │
                                   AgentRunner.async_run_turn()
                                        │
                                   Reply ◀── platform.send()
```

### 11.3 隔离机制

| 维度 | 实现 |
|------|------|
| **用户隔离** | 每用户独立 `SessionStore` + `messages[]` |
| **并发控制** | 每用户 `asyncio.Lock`，防止同一用户消息交错 |
| **平台隔离** | 每平台独立 `dispatcher` task |
| **登录异常** | 失败平台不启动 dispatcher，不影响其他平台 |

### 11.4 当前注册平台

```python
Gateway()
    .register(VoicePlatform(wake_word="你好"))
    # .register(WeChatPlatform())   → 预留
```

---

## 12. 数据流全图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户输入                                      │
│  CLI: sys.stdin / Gateway: Platform.receive()                       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  AgentRunner.run_turn() / async_run_turn()                         │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  1. 记忆召回                                                  │   │
│  │     MemoryStore._auto_recall(user_input)                     │   │
│  │     → hybrid_search(top_k=3)                                 │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐   │
│  │  2. 提示词装配                                                │   │
│  │     build_system_prompt(                                      │   │
│  │       bootstrap_data,  ← BootstrapLoader (8 files)           │   │
│  │       skills_block,    ← SkillsManager                       │   │
│  │       memory_context,  ← MemoryStore._auto_recall()          │   │
│  │       channel          ← terminal / wechat / voice           │   │
│  │     )                                                         │   │
│  │     → 8 层拼接为完整 system prompt                            │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐   │
│  │  3. 追加用户消息 + 持久化                                     │   │
│  │     messages.append({"role": "user", "content": input})      │   │
│  │     store.save_turn("user", input)                           │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐   │
│  │  4. LLM 调用 (含重试)                                        │   │
│  │  ┌─────────────────────────────────────────────────────────┐ │   │
│  │  │  ContextGuard.guard_api_call(system, messages, tools)   │ │   │
│  │  │  → Attempt 0: 直接调用                                   │ │   │
│  │  │  → Attempt 1: 截断工具结果                                │ │   │
│  │  │  → Attempt 2: 压缩历史                                    │ │   │
│  │  │  → Anthropic API / compatible                             │ │   │
│  │  └──────────────────────────────┬──────────────────────────┘ │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │                                       │
│  ┌─────────────────────────▼───────────────────────────────────┐   │
│  │  5. 响应处理                                                │   │
│  │                                                              │   │
│  │  ┌───── end_turn ─────┐  ┌──── tool_use ────┐  ┌─ 其他 ─┐   │   │
│  │  │ 返回文本内容        │  │ 解析 tool block   │  │ 返回文本 │   │   │
│  │  └────────┬──────────┘  │ 调用 handler      │  └────┬───┘   │   │
│  │           │              │ store.save_tool    │       │       │   │
│  │           │              │ 追加 tool_result   │       │       │   │
│  │           │              │ 回到 Step 4 继续   │       │       │   │
│  │           │              └────────┬──────────┘       │       │   │
│  │           └───────────────────────┼──────────────────┘       │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │                                       │
└────────────────────────────┼───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        输出                                         │
│  CLI: print_assistant() / Gateway: Platform.send(Reply)            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 附录：关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CONTEXT_SAFE_LIMIT` | 180000 | Token 安全上限（字符估算） |
| `MAX_TOOL_OUTPUT` | 50000 | 工具输出最大字符数 |
| `MAX_FILE_CHARS` | 20000 | 单文件最大截断字符 |
| `MAX_TOTAL_CHARS` | 150000 | bootstrap 文件总上限 |
| `MAX_SKILLS` | 150 | 最大技能数 |
| `MAX_SKILLS_PROMPT` | 30000 | 技能区块注入上限 |
| `WORKSPACE_DIR` | `./workspace` | 工作区路径 |
| `MODEL` | `config.json` | API key / base_url / model name |

---

## 附录：关键文件索引

| 文件 | 职责 |
|------|------|
| `ultimate.py` | CLI 入口 |
| `cli/cli.py` | 交互式 REPL |
| `gateway/gateway.py` | 多平台消息网关 |
| `agentd/agent/runner.py` | 核心循环 |
| `agentd/bootstrap/container.py` | 依赖容器 |
| `agentd/bootstrap/loader.py` | workspace 文件加载 |
| `agentd/soul/soul.py` | SOUL.md 加载 |
| `agentd/prompt/prompts.py` | 系统提示词装配 |
| `agentd/context/context.py` | 上下文保护 |
| `agentd/context/session.py` | 会话持久化 |
| `agentd/memory/memory.py` | 记忆存储与检索 |
| `agentd/skill/skill.py` | 技能发现与注入 |
| `agentd/tools/tool_handlers.py` | 工具注册总入口 |
| `agentd/tools/file_tools.py` | 文件系统工具 |
| `agentd/tools/memory_tools.py` | 记忆工具 |
| `agentd/tools/browser_tools.py` | 浏览器工具（预留） |
| `config/configs.py` | 全局配置常量 |
| `utils/clients.py` | Anthropic API 客户端 |
| `workspace/*.md` | 7 个 MOSS 风格提示词文件 |
