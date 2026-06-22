# YAML Config — 声明式配置系统

## ADDED Requirements

### YC-LOAD: 配置加载

- **YC-LOAD-1**: `load_config(path)` 从 YAML 文件读取配置，返回 `Config` dataclass 实例
- **YC-LOAD-2**: 文件缺失时打印 "Copy config.example.yaml to config.yaml and edit." 并 exit(1)
- **YC-LOAD-3**: YAML 语法错误时打印行号和具体错误信息，exit(1)
- **YC-LOAD-4**: 必填字段缺失时打印字段完整路径（如 `model.default`），exit(1)
- **YC-LOAD-5**: 默认从项目根目录加载 `config.yaml`，`WORKDIR` 定位

### YC-MODEL: Model 配置段

- **YC-MODEL-1**: `model.default` 指定当前使用的 provider name
- **YC-MODEL-2**: `model.providers` 为 provider 列表，每项含 `name`、`base_url`、`api_key_env`
- **YC-MODEL-3**: 启动时从 `os.environ[provider.api_key_env]` 读取 API key，注入 `provider.api_key`
- **YC-MODEL-4**: `model.default` 指定的 provider 不在 providers 列表中时报错
- **YC-MODEL-5**: `api_key_env` 环境变量未设置时打印 "[NAME]_API_KEY not set. Please export it." 并 exit(1)

### YC-AGENT: Agent 配置段

- **YC-AGENT-1**: `agent.max_iterations` 控制工具调用上限，默认 30
- **YC-AGENT-2**: `agent.context_safe_limit` 控制上下文安全阈值，默认 180000
- **YC-AGENT-3**: `agent.max_tool_output` 控制单个工具输出最大字符数，默认 50000

### YC-TOOLSETS: Toolsets 配置段

- **YC-TOOL-1**: `toolsets.enabled` 列出启用的工具集
- **YC-TOOL-2**: `toolsets.disabled` 列出禁用的工具集

### YC-WORKSPACE: Workspace 配置段

- **YC-WS-1**: `workspace.bootstrap_files` 控制启动时加载的 Bootstrap 文件列表
- **YC-WS-2**: `workspace.max_file_chars` 控制单文件最大字符数
- **YC-WS-3**: `workspace.max_total_chars` 控制 Bootstrap 文件总字符上限

### YC-SKILLS: Skills 配置段

- **YC-SK-1**: `skills.max_skills` 控制最大技能数
- **YC-SK-2**: `skills.max_skills_prompt` 控制技能提示词最大长度

### YC-TEMPLATE: 模板文件

- **YC-TPL-1**: 提供 `config.example.yaml` 作为用户模板，包含所有默认值
- **YC-TPL-2**: `config.example.yaml` 不含 secrets，可安全提交到 git
- **YC-TPL-3**: `config.yaml` 加入 `.gitignore`

### YC-COMPAT: 向后兼容

- **YC-CMP-1**: 模块级别保留旧常量名作为 `config` 对象属性别名（`WORKDIR`、`CONTEXT_SAFE_LIMIT`、`MAX_TOOL_ITERATIONS` 等）
- **YC-CMP-2**: 现有 `from config.configs import ...` 语句继续有效

## 验收场景

1. **正常加载**: `config.yaml` 存在且格式正确 → `load_config()` 返回完整 Config 对象
2. **缺失文件**: `config.yaml` 不存在 → 打印模板提示 → exit(1)
3. **缺失环境变量**: `api_key_env` 指定的环境变量未设置 → 打印变量名 → exit(1)
4. **default 不匹配**: `model.default` 指向不存在的 provider → 打印错误 → exit(1)
5. **YAML 语法错误**: 缩进或格式错误 → 打印行号 + 错误 → exit(1)
6. **模板可用**: `cp config.example.yaml config.yaml` → 填写 api_key_env 对应环境变量 → 正常启动
