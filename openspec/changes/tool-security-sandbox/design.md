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

- `runner.py:process_tool_call()` — 在 handler 调用前后插入 audit + sandbox
- `container.py` — 注入 `Sandbox` 和 `AuditLogger` 实例
- `file_tools.py:tool_bash()/tool_cmd()` — 接受 sandbox 参数，替换内联 blocklist

## 威胁检测分类

| 类别 | 示例 pattern | 动作 |
|------|-------------|------|
| 文件破坏 | `rm -rf /`, `shred`, `wipe` | BLOCK |
| 系统破坏 | `mkfs`, `dd if=`, `> /dev/sd` | BLOCK |
| 信息窃取 | `curl ... | bash`, `/etc/passwd` | BLOCK |
| 路径穿越 | `cd /etc`, `../..` | BLOCK |
| 资源耗尽 | `:(){ :\|:& };:`, `yes > /dev/null` | THROTTLE |

## 测试策略

| 层级 | 覆盖 |
|------|------|
| 单元：环境消毒 | 验证所有父进程 env 被清除，仅白名单通过 |
| 单元：预扫描 | `safe_path` 逻辑应用于命令字符串中的路径 |
| 单元：威胁检测 | 每个分类 ≥ 2 个正例 + 2 个负例 |
| 单元：审计日志 | 记录格式完整、append-only |
| 集成：bash 端到端 | 合法命令通过，危险命令被拦截 |
| 回归：全部现有 | 68+ 个现有测试保持通过 |
