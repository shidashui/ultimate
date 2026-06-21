## 实施任务

### 阶段 1: 基础设施 (独立，先做)

- [x] **Task 1: 创建 IterationBudget**
  - 新建 `agentd/agent/budget.py`
  - `IterationBudget(max_iterations)` 类：`remaining` 属性, `consume()` 方法
  - `config/configs.py` 新增 `MAX_TOOL_ITERATIONS = 30`

- [x] **Task 2: 创建 ToolRegistry**
  - 新建 `agentd/tools/registry.py`
  - `ToolRegistry` 类：`register()`, `get_tools()`, `get_handlers()`, `get_toolsets()`
  - 支持 `toolset` 分类和 `check_fn` 条件可用性
  - 同名工具覆盖时打印 warning

### 阶段 2: 工具迁移 (依赖 Task 2)

- [x] **Task 3: 迁移工具文件到声明式注册**
  - `memory_tools.py`: 改为 `registry.register()` 调用
  - `file_tools.py`: 同上
  - `skill_tools.py`: 同上
  - `browser_tools.py`: 同上（如有工具定义）
  - `tool_handlers.py`: 改为 import 触发注册 + `registry.get_tools()` / `registry.get_handlers()`
  - 保留 `TOOLS` / `TOOL_HANDLERS` 模块级导出变量（由 registry 生成，向后兼容）

### 阶段 3: ContextGuard 升级 (独立)

- [x] **Task 4: ContextGuard 新增预飞压缩**
  - `agentd/context/context.py`: `ContextGuard` 新增 `preflight(system, messages) -> list[dict]`
  - 阈值 `PREFLIGHT_RATIO = 0.8`，超阈值调用 `compact_history()`
  - 保留原有反应式重试逻辑作为兜底（`max_retries` 可从 2 减为 1）
  - 同步和异步版本均支持

### 阶段 4: AgentRunner 核心重构 (依赖 Tasks 1-4)

- [x] **Task 5: AgentRunner 核心重构**
  - `agentd/agent/runner.py`:
    - 删除 `run_turn()` 同步方法，`async_run_turn()` 重命名为 `run_turn()`
    - 新增 `_cached_system_prompt: str | None`，首次构建后缓存
    - `build_system_prompt()` 不再传 `memory_context`（记忆注入 user message）
    - user message 前缀注入记忆上下文
    - 循环引入 `IterationBudget`：`while budget.remaining > 0: budget.consume()`
    - API 调用前执行 `guard.preflight()`
    - 预算耗尽时返回最后一条 assistant text

### 阶段 5: 入口适配 (依赖 Task 5)

- [x] **Task 6: CLI 和 Gateway 适配**
  - `cli/cli.py`: `handle_user_input()` 改用 `asyncio.run(self.runner.run_turn(...))`
  - `cli/cli.py`: `/prompt` 命令适配新的 prompt 构建方式
  - `gateway/gateway.py`: `async_run_turn()` 调用改为 `run_turn()`（方法名变化）
  - `agentd/prompt/prompts.py`: `build_system_prompt()` 不再强制依赖 `memory_context` 参数

### 阶段 6: 验证

- [x] **Task 7: 功能验证**
  - CLI 启动测试：`ultimate chat` 正常启动
  - 基础对话：用户消息 → assistant 回复
  - 工具调用：工具可被 LLM 调用并返回结果
  - 技能加载：`skill_invoke` 正常注册和调度
  - 迭代预算：模拟死循环场景，验证 30 次后自动终止
  - 预飞压缩：长对话触发压缩，验证压缩后正常继续
  - Gateway 验证：`ultimate gateway` 启动正常，平台消息收发正常
