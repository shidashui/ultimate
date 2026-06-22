## ADDED Requirements

### Requirement: hello-skill 可通过 /hello-skill 调用
系统 SHALL 提供 `hello-skill`，用户可通过 `/hello-skill` 命令调用。当调用时，skill SHALL 输出一句问候语并告知调用方式。

#### Scenario: 调用 /hello-skill 返回问候
- **WHEN** 用户输入 `/hello-skill`
- **THEN** skill 输出问候语，包含 "Hello" 字样

#### Scenario: 通过 Skill 工具调用返回相同结果
- **WHEN** Skill 工具以 skill="hello-skill" 调用
- **THEN** 输出与直接 `/hello-skill` 相同

### Requirement: echo-args 可接收并回显参数
系统 SHALL 提供 `echo-args`，接收用户传入的 args 并原样回显。

#### Scenario: 传递参数被回显
- **WHEN** 用户输入 `/echo-args 测试消息`
- **THEN** skill 输出中包含 "测试消息" 或直接回显 args

#### Scenario: 无参数时不报错
- **WHEN** 用户输入 `/echo-args`（无参数）
- **THEN** skill 不报错，输出提示 "No args provided"

### Requirement: system-info 可执行命令输出环境信息
系统 SHALL 提供 `system-info`，可执行 Bash 命令输出当前系统环境信息。

#### Scenario: 调用显示系统信息
- **WHEN** 用户输入 `/system-info`
- **THEN** skill 执行系统命令并输出结果（如当前目录、时间等）

#### Scenario: 命令执行结果包含预期字段
- **WHEN** 用户输入 `/system-info`
- **THEN** 输出中包含 project root 目录名或当前工作目录路径
