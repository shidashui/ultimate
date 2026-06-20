from pathlib import Path
from config.configs import WORKDIR
# ---------------------------------------------------------------------------
# 安全辅助函数
# ---------------------------------------------------------------------------


def safe_path(raw: str) -> Path:
    """
    将用户/模型传入的路径解析为安全的绝对路径.
    防止路径穿越: 最终路径必须在 WORKDIR 之下.
    """
    import sys
    import os

    # 规范化路径分隔符
    if sys.platform == "win32":
        # Windows: 将正斜杠转换为反斜杠，并处理盘符
        raw = raw.replace('/', '\\')
    else:
        # Unix-like: 将反斜杠转换为正斜杠
        raw = raw.replace('\\', '/')

    target = (WORKDIR / raw).resolve()

    # 跨平台的路径检查
    workdir_str = str(WORKDIR.resolve())
    target_str = str(target)

    if sys.platform == "win32":
        # Windows: 大小写不敏感比较
        if not target_str.lower().startswith(workdir_str.lower()):
            raise ValueError(f"Path traversal blocked: {raw} resolves outside WORKDIR")
    else:
        # Unix-like: 大小写敏感比较
        if not target_str.startswith(workdir_str):
            raise ValueError(f"Path traversal blocked: {raw} resolves outside WORKDIR")

    return target


