from pathlib import Path
from src.config.configs import WORKSPACE_DIR

# ---------------------------------------------------------------------------
# 2. 灵魂系统
# ---------------------------------------------------------------------------
# SOUL.md 定义 agent 的人格. 不同 agent 可以有不同的 SOUL.md 文件.
# 注入到系统提示词的靠前位置 -- 越靠前影响力越强.


def load_soul(workspace_dir: Path) -> str:
    path = workspace_dir / "SOUL.md"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""