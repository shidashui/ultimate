from pathlib import Path
import json

CONTEXT_SAFE_LIMIT = 180000
# 工具输出最大字符数 -- 防止超大输出撑爆上下文
MAX_TOOL_OUTPUT = 50000
WORKDIR = Path(__file__).resolve().parent.parent

WORKSPACE_DIR = WORKDIR / "workspace"


# Bootstrap 文件名 -- 每个 agent 启动时加载这 8 个文件
BOOTSTRAP_FILES = [
    "SOUL.md", "IDENTITY.md", "TOOLS.md", "USER.md",
    "HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "MEMORY.md",
]

MAX_FILE_CHARS = 20000
MAX_TOTAL_CHARS = 150000
MAX_SKILLS = 150
MAX_SKILLS_PROMPT = 30000
MAX_TOOL_ITERATIONS = 30

MODEL = json.loads((WORKDIR / "config.json").read_text())["model"]


def get_model_provider():
    """返回基于 config.json 的 BaseProvider 实例。"""
    from agentd.providers import get_provider
    return get_provider(MODEL)
