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
