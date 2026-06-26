"""声明式配置系统 — 从 config.yaml 加载所有运行时配置。

模块级单例通过 get_config() 延迟加载。
向后兼容别名（WORKDIR, CONTEXT_SAFE_LIMIT 等）通过
模块级 __getattr__ 按需解析，保持现有 import 语句有效。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ── Dataclasses ──────────────────────────────────────────────


@dataclass
class ProviderConfig:
    name: str
    model: str
    base_url: str
    api_key_env: str
    api_key: str = ""  # 运行时从 os.environ 注入


@dataclass
class ModelConfig:
    default: str
    providers: list[ProviderConfig]


@dataclass
class ToolsetsConfig:
    enabled: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)


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
class VoiceConfig:
    model: str = "small"
    vad: str = "silero"
    vad_threshold: float = 0.5
    wake_word: str = "你好"
    sample_rate: int = 16000
    max_record_secs: int = 30
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    # 新增
    stt_beam_size: int = 3
    stt_vad_filter: bool = False
    silero_download_timeout: int = 15
    stt_model_warmup: bool = True
    status_verbose: bool = True
    tts_retry_count: int = 3


@dataclass
class Config:
    model: ModelConfig
    toolsets: ToolsetsConfig
    agent: AgentConfig
    workspace: WorkspaceConfig
    skills: SkillsConfig
    voice: VoiceConfig
    workdir: Path
    workspace_dir: Path


# ── Loader ───────────────────────────────────────────────────


def _find_config_path(path: str | Path | None = None) -> Path:
    """确定 config.yaml 路径。默认：<项目根>/config.yaml。"""
    if path is not None:
        return Path(path)
    return Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: str | Path | None = None) -> Config:
    """读取 config.yaml → 校验 → 注入环境变量 → 返回 Config。

    Fail-fast 设计：缺失文件、YAML 语法错误、必填字段缺失、
    环境变量未设置时直接 exit(1)。
    """
    config_path = _find_config_path(path)

    # YC-LOAD-2: missing file
    if not config_path.exists():
        print(
            f"ERROR: No config.yaml found at {config_path}.\n"
            f"  Copy config.example.yaml to config.yaml and edit it:\n"
            f"    cp config/config.example.yaml config.yaml"
        )
        sys.exit(1)

    # YC-LOAD-3: parse error
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"ERROR: Failed to parse {config_path}:\n  {e}")
        sys.exit(1)

    if raw is None:
        print(f"ERROR: {config_path} is empty.")
        sys.exit(1)

    # Parse model
    model_raw = raw.get("model")
    if not model_raw:
        print("ERROR: config.yaml missing 'model' section.")
        sys.exit(1)
    default_name = model_raw.get("default")
    if not default_name:
        print("ERROR: config.yaml missing 'model.default'.")
        sys.exit(1)

    providers = []
    default_provider_raw = None
    for p in model_raw.get("providers", []):
        api_key = p.get("api_key", "")
        api_key_env = p.get("api_key_env", "")
        if not api_key:
            api_key = os.environ.get(api_key_env, "")
        provider = ProviderConfig(
            name=p.get("name", ""),
            model=p.get("model", ""),
            base_url=p.get("base_url", ""),
            api_key_env=api_key_env,
            api_key=api_key,
        )
        if provider.name == default_name:
            default_provider_raw = provider
        providers.append(provider)

    if not providers:
        print("ERROR: config.yaml 'model.providers' is empty.")
        sys.exit(1)

    # YC-MODEL-5: default provider must have its env var set
    if default_provider_raw and not default_provider_raw.api_key:
        print(
            f"ERROR: Environment variable {default_provider_raw.api_key_env} not set.\n"
            f"  Default provider '{default_provider_raw.name}' requires it.\n"
            f"  Please export it: export {default_provider_raw.api_key_env}=<your-api-key>"
        )
        sys.exit(1)

    # YC-MODEL-4: default not found
    if default_provider_raw is None and providers:
        print(
            f"ERROR: model.default '{default_name}' not found in providers list.\n"
            f"  Available: {[p.name for p in providers]}"
        )
        sys.exit(1)

    model = ModelConfig(default=default_name, providers=providers)

    # Parse toolsets
    tools_raw = raw.get("toolsets", {})
    toolsets = ToolsetsConfig(
        enabled=tools_raw.get("enabled", []),
        disabled=tools_raw.get("disabled", []),
    )

    # Parse agent
    agent_raw = raw.get("agent", {})
    agent = AgentConfig(
        max_iterations=agent_raw.get("max_iterations", 30),
        context_safe_limit=agent_raw.get("context_safe_limit", 180000),
        max_tool_output=agent_raw.get("max_tool_output", 50000),
    )

    # Parse workspace
    ws_raw = raw.get("workspace", {})
    workspace = WorkspaceConfig(
        bootstrap_files=ws_raw.get(
            "bootstrap_files",
            ["SOUL.md", "IDENTITY.md", "TOOLS.md", "USER.md",
             "HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "MEMORY.md"],
        ),
        max_file_chars=ws_raw.get("max_file_chars", 20000),
        max_total_chars=ws_raw.get("max_total_chars", 150000),
    )

    # Parse skills
    sk_raw = raw.get("skills", {})
    skills = SkillsConfig(
        max_skills=sk_raw.get("max_skills", 150),
        max_skills_prompt=sk_raw.get("max_skills_prompt", 30000),
    )

    # Parse voice
    voice_raw = raw.get("voice", {})
    voice = VoiceConfig(
        model=voice_raw.get("model", "small"),
        vad=voice_raw.get("vad", "silero"),
        vad_threshold=float(voice_raw.get("vad_threshold", 0.5)),
        wake_word=voice_raw.get("wake_word", "你好"),
        sample_rate=int(voice_raw.get("sample_rate", 16000)),
        max_record_secs=int(voice_raw.get("max_record_secs", 30)),
        tts_voice=voice_raw.get("tts_voice", "zh-CN-XiaoxiaoNeural"),
        stt_beam_size=int(voice_raw.get("stt_beam_size", 3)),
        stt_vad_filter=bool(voice_raw.get("stt_vad_filter", False)),
        silero_download_timeout=int(voice_raw.get("silero_download_timeout", 15)),
        stt_model_warmup=bool(voice_raw.get("stt_model_warmup", True)),
        status_verbose=bool(voice_raw.get("status_verbose", True)),
        tts_retry_count=int(voice_raw.get("tts_retry_count", 3)),
    )

    workdir = config_path.parent
    workspace_dir = workdir / "workspace"

    return Config(
        model=model,
        toolsets=toolsets,
        agent=agent,
        workspace=workspace,
        skills=skills,
        voice=voice,
        workdir=workdir,
        workspace_dir=workspace_dir,
    )


# ── Lazy singleton ───────────────────────────────────────────

_config: Config | None = None


def get_config() -> Config:
    """返回模块级配置单例，首次访问时加载 config.yaml。"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_model_provider():
    """返回基于 config.model 的 BaseProvider 实例。"""
    from agentd.providers import get_provider
    return get_provider(get_config())


# ── Backward compat aliases (YC-CMP-1, YC-CMP-2) ─────────────
# PEP 562: module-level __getattr__ for lazy import compatibility

_ALIAS_MAP: dict[str, callable] = {
    "WORKDIR": lambda: get_config().workdir,
    "WORKSPACE_DIR": lambda: get_config().workspace_dir,
    "MODEL": lambda: get_config().model,
    "CONTEXT_SAFE_LIMIT": lambda: get_config().agent.context_safe_limit,
    "MAX_TOOL_ITERATIONS": lambda: get_config().agent.max_iterations,
    "MAX_TOOL_OUTPUT": lambda: get_config().agent.max_tool_output,
    "BOOTSTRAP_FILES": lambda: get_config().workspace.bootstrap_files,
    "MAX_FILE_CHARS": lambda: get_config().workspace.max_file_chars,
    "MAX_TOTAL_CHARS": lambda: get_config().workspace.max_total_chars,
    "MAX_SKILLS": lambda: get_config().skills.max_skills,
    "MAX_SKILLS_PROMPT": lambda: get_config().skills.max_skills_prompt,
    "VOICE_CONFIG": lambda: get_config().voice,
}


def __getattr__(name: str):
    if name in _ALIAS_MAP:
        return _ALIAS_MAP[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
