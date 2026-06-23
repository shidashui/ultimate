import subprocess
from datetime import datetime, timezone
from utils.print_tools import print_tool
from utils.path_tools import safe_path
from typing import Any
from config.configs import MAX_TOOL_OUTPUT, WORKDIR
from agentd.bootstrap.context import get_current_container
from agentd.tools.sandbox import SandboxBlockedError

def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    """截断过长的输出, 并附上提示."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]"

# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------
# 每个工具函数接收关键字参数 (和 schema 中的 properties 对应),
# 返回字符串结果. 错误通过返回 "Error: ..." 传递给模型.
# ---------------------------------------------------------------------------


def tool_bash(command: str, timeout: int = 30) -> str:
    """执行 shell 命令并返回输出."""
    print_tool("bash", command)

    try:
        sandbox = get_current_container().sandbox
        safe_command, safe_env, warnings, extra_kwargs = sandbox.sanitize(command)
    except SandboxBlockedError as exc:
        return f"Error: Blocked: {exc}"

    try:
        result = subprocess.run(
            safe_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKDIR),
            env=safe_env,
            **extra_kwargs,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate(output) if output else "[no output]"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


def tool_cmd(command: str, timeout: int = 30) -> str:
    """执行 Windows CMD 命令并返回输出."""
    import sys

    if sys.platform != "win32":
        return "Error: 'cmd' tool is only available on Windows. Use 'bash' on Unix-like systems."

    print_tool("cmd", command)

    try:
        sandbox = get_current_container().sandbox
        safe_command, safe_env, warnings, extra_kwargs = sandbox.sanitize(command)
    except SandboxBlockedError as exc:
        return f"Error: Blocked: {exc}"

    try:
        result = subprocess.run(
            safe_command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="cp936",  # Windows中文编码
            timeout=timeout,
            cwd=str(WORKDIR),
            env=safe_env,
            **extra_kwargs,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate(output) if output else "[no output]"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


def tool_read_file(file_path: str) -> str:
    print_tool("read_file", file_path)
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        if not target.is_file():
            return f"Error: Not a file: {file_path}"
        content = target.read_text(encoding="utf-8")
        if len(content) > MAX_TOOL_OUTPUT:
            return content[:MAX_TOOL_OUTPUT] + f"\n... [truncated, {len(content)} total chars]"
        return content
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_list_directory(directory: str = ".") -> str:
    print_tool("list_directory", directory)
    try:
        target = safe_path(directory)
        if not target.exists():
            return f"Error: Directory not found: {directory}"
        if not target.is_dir():
            return f"Error: Not a directory: {directory}"
        entries = sorted(target.iterdir())
        lines = []
        for entry in entries:
            prefix = "[dir]  " if entry.is_dir() else "[file] "
            lines.append(prefix + entry.name)
        return "\n".join(lines) if lines else "[empty directory]"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_get_current_time() -> str:
    print_tool("get_current_time", "")
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d %H:%M:%S UTC")


def tool_write_file(file_path: str, content: str) -> str:
    """写入内容到文件. 父目录不存在时自动创建."""
    print_tool("write_file", file_path)
    try:
        target = safe_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {file_path}"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """
    精确替换文件中的文本.
    old_string 必须在文件中恰好出现一次, 否则报错.
    这和 OpenClaw 的 edit 工具逻辑一致.
    """
    print_tool("edit_file", f"{file_path} (replace {len(old_string)} chars)")
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"

        content = target.read_text(encoding="utf-8")
        count = content.count(old_string)

        if count == 0:
            return "Error: old_string not found in file. Make sure it matches exactly."
        if count > 1:
            return (
                f"Error: old_string found {count} times. "
                "It must be unique. Provide more surrounding context."
            )

        new_content = content.replace(old_string, new_string, 1)
        target.write_text(new_content, encoding="utf-8")
        return f"Successfully edited {file_path}"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# 工具定义: Schema (传给 API) + Handler 调度表
# ---------------------------------------------------------------------------
# 关键认知:
#   TOOLS 数组 = 告诉模型 "你有哪些工具可用"
#   TOOL_HANDLERS 字典 = 告诉我们的代码 "收到工具调用时执行什么函数"
#   两者通过 name 字段关联. 就这么简单.
# ---------------------------------------------------------------------------

from agentd.tools.registry import registry

registry.register(
    name="bash",
    description="Run a shell command and return its output. Use for system commands, git, package managers, etc.",
    parameters={
        "command": {"type": "string", "description": "The shell command to execute."},
        "timeout": {"type": "integer", "description": "Timeout in seconds. Default 30."},
    },
    handler=tool_bash,
    toolset="general",
)

registry.register(
    name="cmd",
    description="Run a Windows CMD command and return its output. Only available on Windows systems.",
    parameters={
        "command": {"type": "string", "description": "The Windows CMD command to execute."},
        "timeout": {"type": "integer", "description": "Timeout in seconds. Default 30."},
    },
    handler=tool_cmd,
    toolset="general",
)

registry.register(
    name="read_file",
    description="Read the contents of a file under the workspace directory.",
    parameters={
        "file_path": {"type": "string", "description": "Path relative to workspace directory."},
    },
    handler=tool_read_file,
    toolset="file",
)

registry.register(
    name="list_directory",
    description="List files and subdirectories in a directory under workspace.",
    parameters={
        "directory": {"type": "string", "description": "Path relative to workspace directory. Default is root."},
    },
    handler=tool_list_directory,
    toolset="file",
)

registry.register(
    name="get_current_time",
    description="Get the current date and time in UTC.",
    parameters={},
    handler=tool_get_current_time,
    toolset="general",
)

registry.register(
    name="write_file",
    description="Write content to a file. Creates parent directories if needed. Overwrites existing content.",
    parameters={
        "file_path": {"type": "string", "description": "Path to the file (relative to working directory)."},
        "content": {"type": "string", "description": "The content to write."},
    },
    handler=tool_write_file,
    toolset="file",
)

registry.register(
    name="edit_file",
    description="Replace an exact string in a file with a new string. The old_string must appear exactly once in the file.",
    parameters={
        "file_path": {"type": "string", "description": "Path to the file (relative to working directory)."},
        "old_string": {"type": "string", "description": "The exact text to find and replace. Must be unique."},
        "new_string": {"type": "string", "description": "The replacement text."},
    },
    handler=tool_edit_file,
    toolset="file",
)

# 向后兼容的模块级导出
_file_tool_names = {"bash", "cmd", "read_file", "list_directory", "get_current_time", "write_file", "edit_file"}
TOOLS = [t for t in registry.get_tools() if t["name"] in _file_tool_names]
TOOL_HANDLERS: dict[str, Any] = {
    "bash": tool_bash,
    "cmd": tool_cmd,
    "read_file": tool_read_file,
    "list_directory": tool_list_directory,
    "get_current_time": tool_get_current_time,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
}

if __name__ == "__main__":
    # 简单测试工具函数
    print(tool_cmd("dir"))
