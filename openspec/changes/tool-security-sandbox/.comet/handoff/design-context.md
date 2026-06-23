# Comet Design Handoff

- Change: tool-security-sandbox
- Phase: design
- Mode: compact
- Context hash: 4123389bfd394235a493d4c5c086cd922874c514a0bfec07c4c5581302e76400

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/tool-security-sandbox/proposal.md

- Source: openspec/changes/tool-security-sandbox/proposal.md
- Lines: 1-32
- SHA256: f86835f97c9f611067763e252810a6cad81951f16b835268d146582aa66c4ff5

```md
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
```

## openspec/changes/tool-security-sandbox/design.md

- Source: openspec/changes/tool-security-sandbox/design.md
- Lines: 1-104
- SHA256: 983ccc8e6cff7a4834dc30da9f5b56805a8eb46f95c10c30dc0a35b231580c6f

[TRUNCATED]

```md
## 架构决策

### 方案选型：A+B 混合（多层防御 + OS 沙箱扩展点）

- **方案 A（多层防御，必选）**：纯 Python 实现的环境变量白名单 + 命令预扫描 + 增强威胁检测
- **方案 B（OS 沙箱，可选扩展）**：bwrap (Linux) / sandbox-exec (macOS) / Job Objects (Windows) — 系统可用时自动启用，不可用时静默降级到方案 A
- **放弃方案 C**：`shell=True → shell=False` 破坏性太大，LLM 大量依赖管道和重定向语法

### 防御层次

```
process_tool_call("bash", {"command": "rm -rf /tmp/foo"})
  │
  ├─ 第 0 层：审计日志入口（记录 tool_name + params）
  │
  ├─ 第 1 层：环境变量消毒
  │   env_whitelist → {"PATH": ..., "HOME": WORKDIR, "TEMP": ...}
  │   原有 env 全部丢弃（含 API key、secrets）
  │
  ├─ 第 2 层：命令预扫描
  │   解析命令中的路径引用，用 safe_path() 逻辑校验
  │   检测明显的路径穿越（../、绝对路径指向 WORKDIR 外部）
  │
  ├─ 第 3 层：威胁检测（分类 pattern）
  │   替换现有的 4 行 substring blocklist
  │   分类：文件破坏、系统破坏、信息窃取、权限提升、fork bomb
  │
  ├─ 第 4 层：OS 沙箱（可选，自动检测）
  │   Linux: bwrap --bind WORKDIR /workdir --dev /dev --proc /proc
  │   macOS: sandbox-exec (限制文件写入到 WORKDIR)
  │   Windows: Job Objects (限制进程能力)
  │   不可用 → 静默降级
  │
  ├─ subprocess.run(sanitized_command, env=safe_env, ...)
  │
  └─ 第 5 层：审计日志出口（记录 result + duration）
```

### 关键设计原则

- **零外部依赖**：多层防御核心用 Python stdlib 实现
- **降级优雅**：OS 沙箱不可用时静默降级，不阻塞 tool call
- **审计不可变**：审计日志 append-only，不暴露给 LLM
- **向后兼容**：合法命令零影响，仅拦截/消毒恶意模式

## 组件设计

### Sandbox (新增 `agentd/tools/sandbox.py`)

```python
class Sandbox:
    """命令执行沙箱 — 多层防御协调器"""
    def __init__(self, workdir: Path, env_whitelist: set[str] | None = None)
    def sanitize_env(self) -> dict[str, str]        # 环境变量消毒
    def prescan(self, command: str) -> list[str]      # 命令预扫描 → 返回告警列表
    def detect_threats(self, command: str) -> list[str]  # 威胁检测 → 返回命中规则
    def os_sandbox_args(self) -> dict                 # OS 沙箱参数（如可用）
    def wrap_command(self, command: str) -> str       # 包装命令（如 bwrap 前缀）
```

### Audit (新增 `agentd/tools/audit.py`)

```python
@dataclass
class AuditRecord:
    timestamp: str
    tool_name: str
    params: dict
    result_summary: str     # 前 200 字符
    duration_ms: float
    warnings: list[str]
    success: bool

class AuditLogger:
    def log(self, record: AuditRecord) -> None
    def recent(self, n: int = 100) -> list[AuditRecord]
```

### 集成点

```

Full source: openspec/changes/tool-security-sandbox/design.md

## openspec/changes/tool-security-sandbox/tasks.md

- Source: openspec/changes/tool-security-sandbox/tasks.md
- Lines: 1-47
- SHA256: b9ae77bf97d2a85b81a440d630c5d80f1716a7f697802bfced5b560a75e14379

```md
## 实施任务

### 阶段 1: 基础设施

- [ ] **Task 1: 创建审计日志模块** (`agentd/tools/audit.py`)
  - AuditRecord dataclass + AuditLogger 类
  - 结构化日志，append-only，支持 `recent(n)` 查询
  - 集成到 `process_tool_call()`

- [ ] **Task 2: 创建沙箱核心模块** (`agentd/tools/sandbox.py`)
  - `Sandbox` 类：环境消毒 + 命令预扫描 + 威胁检测
  - `_validate_paths_in_command()` — 提取命令中的路径并 safe_path 校验
  - `_detect_threats()` — 分类 pattern 匹配（替换当前 4 行 substring blocklist）
  - `_build_safe_env()` — 环境变量白名单过滤

- [ ] **Task 3: OS 沙箱适配层** (扩展 `sandbox.py`)
  - `_detect_os_sandbox()` — 自动检测 bwrap/sandbox-exec/Job Objects
  - `_wrap_command()` — 可用时包装命令，不可用时返回原命令
  - 静默降级逻辑

### 阶段 2: 集成

- [ ] **Task 4: 集成沙箱到 Bash/Cmd 工具**
  - `tool_bash()` / `tool_cmd()` 使用 Sandbox 替换内联 blocklist
  - 环境变量消毒在 subprocess.run 之前执行
  - 威胁检测失败时返回结构化错误（含命中规则名）

- [ ] **Task 5: 集成审计到 process_tool_call**
  - handler 调用前后记录 AuditRecord
  - runner.py 注入 AuditLogger，记录每次 tool call
  - 审计日志不暴露给 LLM（内部日志文件）

- [ ] **Task 6: Container 注入**
  - Container 创建 Sandbox(workdir=WORKDIR) 和 AuditLogger 实例
  - 通过现有 ContextVar 机制传递给 tools

### 阶段 3: 测试与验证

- [ ] **Task 7: 沙箱安全测试**
  - 环境消毒测试（验证 API key 被清除）
  - 命令预扫描测试（路径穿越 blocked，合法路径 pass）
  - 威胁检测测试（每分类 2+ 正例 + 2+ 负例）
  - OS 沙箱降级测试（bwrap 不可用时静默降级）

- [ ] **Task 8: 审计日志测试 + 回归验证**
  - 审计记录格式完整
  - 全量回归测试通过（68+ 现有 + 新增）
```

## openspec/changes/tool-security-sandbox/specs/audit-log/spec.md

- Source: openspec/changes/tool-security-sandbox/specs/audit-log/spec.md
- Lines: 1-34
- SHA256: c203b429d2f097457319b97ac54d10aa1c463edf03ecb14513e11e683ad1a2ce

```md
## ADDED Requirements

### Requirement: Tool Call 审计日志

每次 tool call 执行 SHALL 记录结构化审计日志到 JSONL 文件。

#### Scenario: 记录格式

- **WHEN** 任意 tool call 执行完成（成功或失败）
- **THEN** SHALL 追加一行 JSON 到 `logs/audit/YYYY-MM-DD.jsonl`
- **AND** JSON 对象 SHALL 包含字段: `ts`, `session`, `tool`, `params`, `result`, `dur_ms`, `warnings`, `blocked`

#### Scenario: 被拦截记录

- **WHEN** Sandbox 因威胁检测 BLOCK 命令执行
- **THEN** 审计记录 SHALL 包含 `"blocked": true`
- **AND** `result` SHALL 包含命中规则名

#### Scenario: 日志轮转

- **WHEN** 日期变更
- **THEN** 审计日志 SHALL 写入新的 `YYYY-MM-DD.jsonl` 文件

#### Scenario: 过期清理

- **WHEN** 审计日志文件超过 `max_days`（默认 30 天）
- **THEN** `cleanup()` SHALL 删除过期文件
- **AND** SHALL 返回删除文件数

#### Scenario: 写入失败不影响执行

- **WHEN** 审计日志写入失败（磁盘满、权限等）
- **THEN** tool call SHALL 正常完成
- **AND** 写入错误 SHALL 通过 `logger.error` 记录
```

## openspec/changes/tool-security-sandbox/specs/env-isolation/spec.md

- Source: openspec/changes/tool-security-sandbox/specs/env-isolation/spec.md
- Lines: 1-31
- SHA256: daa657234048c5a876c8d5ec4182488e574ba739f61d544222ebcebfd102667c

```md
## ADDED Requirements

### Requirement: 子进程环境变量隔离

执行外部命令（`bash`/`cmd`）时 SHALL 清除父进程所有环境变量，仅传递安全白名单。

#### Scenario: 默认白名单生效

- **WHEN** 创建 Sandbox 实例时未指定自定义 `env_whitelist`
- **THEN** `build_safe_env()` SHALL 仅返回以下环境变量（若父进程中存在）:
  - `PATH` — 保留原始值
  - `HOME` — 设置为 WORKDIR 路径
  - `USER` 或 `USERNAME` — 保留原始值
  - `TEMP` 或 `TMP` — 保留原始值
  - `SYSTEMROOT` — 仅 Windows
  - `SHELL` — 仅 Unix

#### Scenario: 自定义白名单

- **WHEN** 创建 Sandbox 时传入 `env_whitelist={"PATH", "HOME", "MY_VAR"}`
- **THEN** `build_safe_env()` SHALL 仅返回白名单中存在的变量

#### Scenario: 敏感变量被清除

- **WHEN** 父进程中存在 `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN` 等变量
- **THEN** 这些变量 SHALL NOT 出现在 `build_safe_env()` 返回的字典中

#### Scenario: 白名单变量在父进程中不存在

- **WHEN** 白名单中的某个变量在父进程中不存在
- **THEN** `build_safe_env()` SHALL 静默忽略该变量，不报错
```

## openspec/changes/tool-security-sandbox/specs/tool-sandbox/spec.md

- Source: openspec/changes/tool-security-sandbox/specs/tool-sandbox/spec.md
- Lines: 1-52
- SHA256: ddad7d9c39f866f2cc5e25a5e1a690ef018254626904e06af824bcc62c4befdc

```md
## ADDED Requirements

### Requirement: 命令执行多层防御

`tool_bash()` 和 `tool_cmd()` 在执行 shell 命令前 SHALL 通过 Sandbox 组件的多层防御检查。

#### Scenario: 环境变量消毒

- **WHEN** 执行任意 shell 命令
- **THEN** 子进程环境变量 SHALL 仅包含白名单中的变量（默认: `PATH`, `HOME`, `USER`, `USERNAME`, `TEMP`, `TMP`, `SYSTEMROOT`, `SHELL`）
- **AND** 父进程中的 API key、token、secrets 等敏感环境变量 SHALL NOT 传递给子进程

#### Scenario: 路径穿越检测

- **WHEN** 命令字符串包含绝对路径（如 `/etc/passwd`）或相对穿越路径（如 `../../sensitive`）
- **AND** 该路径解析后不在 WORKDIR 内
- **THEN** Sandbox SHALL 拒绝执行，返回 BLOCK 级别错误

#### Scenario: 威胁检测 — 文件破坏

- **WHEN** 命令字符串匹配文件破坏 pattern（如 `rm -rf /`, `shred`, `wipe`, `del /f /s /q`）
- **THEN** Sandbox SHALL 拒绝执行，抛出 `SandboxBlockedError` 包含命中规则名
- **AND** `process_tool_call` SHALL 返回 `Error: Blocked: <rule>` 给 LLM

#### Scenario: 威胁检测 — 系统破坏

- **WHEN** 命令字符串匹配系统破坏 pattern（如 `mkfs`, `dd if=`, `format`, `diskpart`）
- **THEN** Sandbox SHALL 拒绝执行，行为同文件破坏

#### Scenario: 威胁检测 — 信息窃取

- **WHEN** 命令字符串匹配信息窃取 pattern（如 `curl ... | bash`, `wget ... | sh`, `/etc/shadow`）
- **THEN** Sandbox SHALL 拒绝执行，行为同文件破坏

#### Scenario: 威胁检测 — 路径穿越/资源滥用 (WARN)

- **WHEN** 命令字符串匹配 WARN 级 pattern（如 `cd /etc`, fork bomb `:(){ :|:& };:`）
- **THEN** Sandbox SHALL 允许执行
- **AND** SHALL 记录 warning 到审计日志

#### Scenario: 合法命令正常执行

- **WHEN** 命令不匹配任何威胁 pattern 且路径均在 WORKDIR 内
- **THEN** 命令 SHALL 正常执行，与当前行为一致
- **AND** 环境变量 SHALL 已消毒

#### Scenario: OS 沙箱可选降级

- **WHEN** 系统未安装 bwrap/sandbox-exec 或平台不支持 Job Objects
- **THEN** `os_sandbox_available()` SHALL 返回 `False`
- **AND** `wrap_command()` SHALL 返回原命令（不包装）
- **AND** L1-L3 防御层 SHALL 仍然生效
```

