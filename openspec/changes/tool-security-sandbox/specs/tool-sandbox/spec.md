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
