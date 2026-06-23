## Why

当前 Agent Tools 层缺少真正的安全沙箱。Bash/Cmd 命令以 `shell=True` 执行，完全继承父进程环境变量（含 API key），加上仅 4 个字符串子串匹配的"危险命令检测"，形同虚设。LLM 可能被 prompt injection 诱导执行 `rm -rf /*`、读取 `/etc/passwd` 等危险操作。需要在 tool call 调度层增加防御纵深，将命令执行和敏感信息访问限制在项目目录边界内。

## What Changes

- **Bash/Cmd 命令沙箱**：多层防御架构 — 环境变量白名单 + 命令预扫描（路径穿越检测）+ 增强威胁检测（分类 pattern 替换简单子串匹配）+ OS 原生沙箱扩展点（bwrap/sandbox-exec/Job Objects）
- **环境变量隔离**：执行 shell 命令前清除所有继承的环境变量，仅传递安全白名单（PATH、HOME=WORKDIR、TEMP 等），防止 API key 等敏感信息泄露
- **审计日志**：结构化记录每次 tool call（工具名、参数、时间戳、执行结果），支持事后安全审计
- **文件操作**：已有 `safe_path()` 路径穿越防护，本次不做重复加固

## Capabilities

### New Capabilities

- `tool-sandbox`: Bash/Cmd 命令执行沙箱 — 多层防御（预扫描 + 威胁检测 + OS 沙箱扩展点），确保命令操作限制在项目目录内
- `env-isolation`: 环境变量隔离 — 执行外部进程前清除继承环境，仅传递白名单变量
- `audit-log`: Tool call 审计日志 — 结构化记录工具调用全链路信息

### Modified Capabilities

_（无已有 capability 的规格级变更）_

## Impact

- **`agentd/tools/file_tools.py`**: `tool_bash()` / `tool_cmd()` — 集成沙箱层
- **新增 `agentd/tools/sandbox.py`**: 沙箱核心模块（预扫描、威胁检测、OS 沙箱适配）
- **新增 `agentd/tools/audit.py`**: 审计日志模块
- **`agentd/bootstrap/container.py`**: 沙箱和审计组件注入
- **`agentd/agent/runner.py`**: `process_tool_call()` 增加审计记录
- **`tests/test_sandbox.py`**: 沙箱安全测试
- **`tests/test_audit.py`**: 审计日志测试
