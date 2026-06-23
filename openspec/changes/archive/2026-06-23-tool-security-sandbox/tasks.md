## 实施任务

### 阶段 1: 基础设施

- [x] **Task 1: 创建审计日志模块** (`agentd/tools/audit.py`)
  - AuditRecord dataclass + AuditLogger 类
  - 结构化日志，append-only，支持 `recent(n)` 查询
  - 集成到 `process_tool_call()`

- [x] **Task 2: 创建沙箱核心模块** (`agentd/tools/sandbox.py`)
  - `Sandbox` 类：环境消毒 + 命令预扫描 + 威胁检测
  - `_validate_paths_in_command()` — 提取命令中的路径并 safe_path 校验
  - `_detect_threats()` — 分类 pattern 匹配（替换当前 4 行 substring blocklist）
  - `_build_safe_env()` — 环境变量白名单过滤

- [x] **Task 3: OS 沙箱适配层** (扩展 `sandbox.py`)
  - `_detect_os_sandbox()` — 自动检测 bwrap/sandbox-exec/Job Objects
  - `_wrap_command()` — 可用时包装命令，不可用时返回原命令
  - 静默降级逻辑

### 阶段 2: 集成

- [x] **Task 4: 集成沙箱到 Bash/Cmd 工具**
  - `tool_bash()` / `tool_cmd()` 使用 Sandbox 替换内联 blocklist
  - 环境变量消毒在 subprocess.run 之前执行
  - 威胁检测失败时返回结构化错误（含命中规则名）

- [x] **Task 5: 集成审计到 process_tool_call**
  - handler 调用前后记录 AuditRecord
  - runner.py 注入 AuditLogger，记录每次 tool call
  - 审计日志不暴露给 LLM（内部日志文件）

- [x] **Task 6: Container 注入**
  - Container 创建 Sandbox(workdir=WORKDIR) 和 AuditLogger 实例
  - 通过现有 ContextVar 机制传递给 tools

### 阶段 3: 测试与验证

- [x] **Task 7: 沙箱安全测试**
  - 环境消毒测试（验证 API key 被清除）
  - 命令预扫描测试（路径穿越 blocked，合法路径 pass）
  - 威胁检测测试（每分类 2+ 正例 + 2+ 负例）
  - OS 沙箱降级测试（bwrap 不可用时静默降级）

- [x] **Task 8: 审计日志测试 + 回归验证**
  - 审计记录格式完整
  - 全量回归测试通过（68+ 现有 + 新增）
