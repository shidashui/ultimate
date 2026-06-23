---
comet_change: tool-security-sandbox
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-23-tool-security-sandbox
status: final
---

# Tool Security Sandbox — 技术设计

## 架构

```
                      process_tool_call("bash", {command, timeout})
                                    │
                      ┌─────────────┴─────────────┐
                      │   AuditLogger.entry()     │  审计入口
                      │   (JSONL append-only)     │
                      └─────────────┬─────────────┘
                                    │
                      ┌─────────────┴─────────────┐
                      │   Sandbox.sanitize()      │  多层防御
                      │                            │
                      │   L1: env_whitelist()     │  环境消毒
                      │   L2: prescan_paths()     │  路径预扫描
                      │   L3: detect_threats()    │  威胁分类检测
                      │   L4: os_sandbox_wrap()   │  OS 沙箱 (可选)
                      │                            │
                      │   → subprocess.run(...)   │
                      └─────────────┬─────────────┘
                                    │
                      ┌─────────────┴─────────────┐
                      │   AuditLogger.exit()      │  审计出口
                      │   (result + duration)     │
                      └───────────────────────────┘
```

## 分层职责

| 层 | 模块 | 职责 |
|----|------|------|
| 审计 | `agentd/tools/audit.py` | JSONL 日志，按天轮转，记录 tool_name/params/result/duration |
| 沙箱协调 | `agentd/tools/sandbox.py` | Sandbox 类 — 环境消毒 + 命令预扫描 + 威胁检测 + OS 沙箱 |
| 注入 | `agentd/bootstrap/container.py` | 初始化 Sandbox + AuditLogger，通过 ContextVar 暴露 |
| 调用点 | `agentd/agent/runner.py` | process_tool_call 增审计包裹 |
| 执行 | `agentd/tools/file_tools.py` | tool_bash/cmd 通过 Container 获取 Sandbox 执行消毒 |

## Sandbox 组件

### 注入方式：ContextVar

与现有 Container 模式完全一致。`tool_bash()` 通过 `get_current_container().sandbox` 获取实例。

### 防御层

**L1 — 环境消毒** (`build_safe_env`):
- 清除所有继承环境变量
- 默认白名单: `PATH`, `HOME(=WORKDIR)`, `USER`/`USERNAME`, `TEMP`/`TMP`, `SYSTEMROOT`(Windows), `SHELL`(Unix)
- API key、secrets、token 等敏感变量全部丢弃

**L2 — 路径预扫描** (`prescan_paths`):
- 提取命令字符串中的路径引用
- 对每个候选路径执行 `safe_path()` 校验
- 检测: 绝对路径 (`/etc/passwd`), 相对穿越 (`../../`), 环境变量展开 (`$HOME/.ssh`)
- 返回非法路径列表

**L3 — 威胁检测** (`detect_threats`):
- 分类 pattern 匹配，替换现有 [file_tools.py:25-28] 的 4 行 substring blocklist
- 返回 `(severity, matched_rules[])`

| 类别 | 示例 pattern | 级别 |
|------|-------------|------|
| 文件破坏 | `rm -rf /`, `shred`, `wipe`, `del /f /s` | BLOCK |
| 系统破坏 | `mkfs`, `dd if=`, `format`, `diskpart` | BLOCK |
| 信息窃取 | `curl \| bash`, `wget \| sh`, `/etc/shadow` | BLOCK |
| 路径穿越 | `cd /etc`, `../..` | WARN |
| 资源滥用 | `:(){ :\|:& };:`, `yes >`, `while true;do` | WARN |

**L4 — OS 沙箱** (`os_sandbox_available` + `wrap_command`):
- 自动检测 bwrap (Linux) / sandbox-exec (macOS) / Job Objects (Windows)
- 可用 → 包装命令; 不可用 → 静默降级，返回原命令

### Sandbox.sanitize() 返回值

```python
def sanitize(self, command: str) -> tuple[str, dict[str, str], list[str]]:
    """返回 (safe_command, safe_env, warnings)。
    BLOCK 级威胁 → 抛出 SandboxBlockedError。
    """
```

## AuditLogger 组件

### 存储格式

`logs/audit/YYYY-MM-DD.jsonl`，每行一条 JSON:

```jsonl
{"ts":"2026-06-23T15:30:00Z","session":"abc","tool":"bash","params":{"command":"ls"},"result":"ok","dur_ms":12,"warnings":[],"blocked":false}
```

### AuditRecord

```python
@dataclass
class AuditRecord:
    timestamp: str       # ISO 8601
    session_id: str
    tool_name: str
    params: dict
    result_summary: str  # 前 200 字符
    duration_ms: float
    warnings: list[str]
    blocked: bool
```

### 生命周期

- `log(record)` — 追加一行到当日文件（线程安全）
- `recent(n)` — 读取最新 N 条
- `cleanup()` — 删除超过 `max_days`（默认 30）的旧文件

## 威胁响应策略

| 级别 | 行为 |
|------|------|
| BLOCK | 抛出 `SandboxBlockedError` → `process_tool_call` 返回 `Error: Blocked: <rule>` → LLM 生成替代方案 |
| WARN | 允许执行，记录到 AuditRecord.warnings + logger.warning |

## 错误处理

- `SandboxBlockedError` 包含命中规则名和严重级别，LLM 可据此调整命令
- OS 沙箱不可用时静默降级，不阻塞合法命令
- 审计日志写入失败不影响 tool call 执行（logger.error + 继续）

## 边界条件

| 输入 | 行为 |
|------|------|
| 合法命令 `echo hi` | env 消毒 → 无威胁 → 无路径违规 → 正常执行 |
| 危险命令 `rm -rf /` | L3 BLOCK → SandboxBlockedError → 审计 blocked=true |
| 路径穿越 `cat /etc/passwd` | L2 检测 `/etc/passwd` 非法 → BLOCK |
| 管道命令 `curl ... \| bash` | L3 检测信息窃取 pattern → BLOCK |
| bwrap 未安装 | L4 检测不可用 → 静默降级 → L1-L3 仍生效 |
| 空命令 `""` | L3 不做匹配 → 正常流程（subprocess 自身报错） |

## 测试策略

| 层级 | 覆盖 | 位置 |
|------|------|------|
| 单元: 环境消毒 | 验证 env 清除，仅白名单通过 | `tests/test_sandbox.py` |
| 单元: 路径预扫描 | safe_path 逻辑应用于命令中的路径 | 同上 |
| 单元: 威胁检测 | 每分类 ≥ 2 正例 + 2 负例 | 同上 |
| 单元: 审计日志 | 格式完整、append、cleanup | `tests/test_audit.py` |
| 集成: bash 端到端 | 合法通过，危险被拦截，审计有记录 | `tests/test_sandbox.py` |
| 回归: 全部 | 68+ 现有测试保持通过 | `tests/` |

## 风险

| 风险 | 缓解 |
|------|------|
| 命令预扫描有漏网路径 | 仅作为纵深防御一层，L3 威胁检测兜底 |
| 环境白名单遗漏必要变量 | 默认白名单覆盖常用 OS，支持 `env_whitelist` 自定义 |
| OS 沙箱不可用导致无真正隔离 | 静默降级 + L1-L3 仍提供显著保护（比现状好一个数量级） |
| 审计日志磁盘占用 | 按天轮转 + 30 天自动清理 |
