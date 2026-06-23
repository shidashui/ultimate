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
