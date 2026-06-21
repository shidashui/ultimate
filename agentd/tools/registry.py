from utils.print_tools import print_warn


class ToolRegistry:
    """声明式工具注册表。"""

    def __init__(self):
        self._tools: list[dict] = []
        self._handlers: dict[str, callable] = {}
        self._tool_to_toolset: dict[str, str] = {}
        self._toolsets: dict[str, list[str]] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, dict],
        handler: callable,
        toolset: str = "general",
        check_fn: callable | None = None,
    ) -> None:
        """声明式注册一个工具。

        Args:
            name: 工具名称（唯一标识，与 Anthropic API tool name 对应）
            description: 工具描述（注入 tool schema）
            parameters: 参数定义 dict，key 为参数名，value 为 {"type": "...", "description": "..."}
            handler: 工具执行函数，接受关键字参数，返回字符串
            toolset: 工具集分类（file, memory, skill, browser, general）
            check_fn: 条件可用性检查，返回 False 时跳过注册
        """
        if check_fn is not None and not check_fn():
            return

        if name in self._handlers:
            print_warn(f"Tool '{name}' 被覆盖")

        schema = {
            "name": name,
            "description": description,
            "input_schema": {
                "type": "object",
                "properties": parameters,
                "required": list(parameters.keys()),
            },
        }
        self._tools.append(schema)
        self._handlers[name] = handler
        self._tool_to_toolset[name] = toolset
        self._toolsets.setdefault(toolset, []).append(name)

    def get_tools(self, enabled_toolsets: set[str] | None = None) -> list[dict]:
        """返回工具 schema 列表，可按 toolset 过滤。"""
        if enabled_toolsets is None:
            return list(self._tools)
        return [
            t for t in self._tools
            if self._tool_to_toolset.get(t["name"]) in enabled_toolsets
        ]

    def get_handlers(self) -> dict[str, callable]:
        """返回 {name: handler} 映射。"""
        return dict(self._handlers)

    def get_toolsets(self) -> dict[str, list[str]]:
        """返回 {toolset: [tool_names]} 映射。"""
        return {k: list(v) for k, v in self._toolsets.items()}


# 全局单例 — 模块加载时创建，工具文件 import 时自注册
registry = ToolRegistry()
