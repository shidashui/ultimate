---
comet_change: declarative-yaml-config
role: technical-design
canonical_spec: openspec
---

# 声明式 YAML 配置 — 技术设计

## 背景

当前配置系统：
- `config.json` 明文存储 API key，gitignored 但仍以明文存在于本地文件系统
- `config/configs.py` 混合了路径常量、启动配置、运行时参数，全部硬编码为 Python 常量
- `config.json` 的 `model.provider` 字段存在但从未被代码用于多 provider 分发
- 无 `config.example.*` 模板文件，新用户需凭空创建

## 核心接口

### Config 数据类

```python
# config/configs.py

@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str
    api_key: str = ""  # os.environ[api_key_env] 注入

@dataclass
class ModelConfig:
    default: str
    providers: list[ProviderConfig]

@dataclass
class ToolsetsConfig:
    enabled: list[str]
    disabled: list[str]

@dataclass
class AgentConfig:
    max_iterations: int = 30
    context_safe_limit: int = 180000
    max_tool_output: int = 50000

@dataclass
class WorkspaceConfig:
    bootstrap_files: list[str] = field(default_factory=lambda: [
        "SOUL.md", "IDENTITY.md", "TOOLS.md", "USER.md",
        "HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "MEMORY.md",
    ])
    max_file_chars: int = 20000
    max_total_chars: int = 150000

@dataclass
class SkillsConfig:
    max_skills: int = 150
    max_skills_prompt: int = 30000

@dataclass
class Config:
    model: ModelConfig
    toolsets: ToolsetsConfig
    agent: AgentConfig
    workspace: WorkspaceConfig
    skills: SkillsConfig
    workdir: Path
    workspace_dir: Path

def load_config(path: str | Path = None) -> Config: ...
```

### 向后兼容别名

```python
# config/configs.py 模块级别（import 时可用）
WORKDIR = config.workdir
WORKSPACE_DIR = config.workspace_dir
CONTEXT_SAFE_LIMIT = config.agent.context_safe_limit
MAX_TOOL_ITERATIONS = config.agent.max_iterations
MAX_TOOL_OUTPUT = config.agent.max_tool_output
BOOTSTRAP_FILES = config.workspace.bootstrap_files
MAX_FILE_CHARS = config.workspace.max_file_chars
MAX_TOTAL_CHARS = config.workspace.max_total_chars
MAX_SKILLS = config.skills.max_skills
MAX_SKILLS_PROMPT = config.skills.max_skills_prompt
```

## 设计决策

| # | 决策 | 理由 |
|---|------|------|
| 1 | YAML 格式 | 注释支持、Python 原生 `pyyaml`、可读性优于 JSON |
| 2 | 统一 Config dataclass | 单一事实源，所有配置值在一处，类型安全 |
| 3 | 模块单例 `config = load_config()` | 简单，所有 import 方立即可用，启动即校验 |
| 4 | `api_key_env` + 环境变量 | 不允许明文密钥，Docker/CI 友好 |
| 5 | 模块级别名向后兼容 | 最小化 consumer 改动，渐进迁移 |
| 6 | `config.yaml` 项目根目录 | 约定优于配置，通过 `WORKDIR` 定位 |
| 7 | `config.example.yaml` 提交 git | 新用户直接 `cp config.example.yaml config.yaml` |
| 8 | `config.yaml` gitignored | 防止密钥泄露 |

## 错误处理

| 场景 | 行为 |
|------|------|
| `config.yaml` 缺失 | 打印 "Copy config.example.yaml to config.yaml and edit." 并 exit(1) |
| `api_key_env` 环境变量未设置 | 打印 "[NAME]_API_KEY not set. Please export it." 并 exit(1) |
| YAML 解析失败 | 打印行号 + 具体错误，exit(1) |
| 必填字段缺失 | 打印缺失字段完整路径（如 `model.default`），exit(1) |

设计原则：**启动失败是好的失败**。不在运行时默默 fallback 到不安全的默认值。

## 文件变更

```text
新建:  config/config.example.yaml       # 用户模板（含所有默认值，除 secrets）
废弃:  config/config.json               # 删除

重写:  config/configs.py                # 常量 → Config dataclass + load_config()

修改:  agentd/providers/__init__.py     # get_provider(config) 适配多 provider
修改:  agentd/bootstrap/container.py    # 用 config 对象
修改:  agentd/context/context.py        # CONTEXT_SAFE_LIMIT → config.agent.context_safe_limit
修改:  agentd/agent/runner.py           # MAX_TOOL_ITERATIONS → config.agent.max_iterations
修改:  cli/cli.py                       # MODEL['name'] → config.model
修改:  agentd/prompt/prompts.py         # MODEL → config.model
修改:  requirements.txt                 # +pyyaml
修改:  .gitignore                       # config.json → config.yaml
```

## 数据流

```text
config.yaml ──→ load_config() ──→ Config 实例 (模块单例)
                     │
     ┌───────────────┼───────────────────┐
     ▼               ▼                    ▼
 get_provider()  ContextGuard()    AgentRunner()
   │               │                  │
   ▼               ▼                  ▼
 AnthropicProvider  config.agent      config.agent
 (api_key 来自      .context_safe_    .max_iterations
  os.environ)       limit
```

## 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| 现有用户无 `config.yaml` | 低 | `config.example.yaml` 模板；出错信息指向模板 |
| `pyyaml` 未安装 | 低 | 加入 `requirements.txt` |
| 环境变量未设置 | 中 | 启动时明确报错，指示具体变量名 |
| consumer 遗漏更新 | 中 | 全量搜索 `MODEL`/`CONTEXT_SAFE_LIMIT`/`MAX_TOOL_ITERATIONS` 引用 |

## 测试策略

1. **Config 加载单元测试** — mock `yaml.safe_load`，验证各字段解析 + 默认值 + 必填校验
2. **Provider 工厂测试** — mock `os.environ`，验证多 provider 分发 + api_key_env 注入
3. **错误路径测试** — 缺失文件、缺失字段、缺失环境变量，验证清晰报错
4. **回归** — `python ultimate.py` 启动 → 输入消息 → AI 正常回复
