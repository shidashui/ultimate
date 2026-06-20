from agentd.bootstrap import container
from utils.print_tools import print_tool
from typing import Any

# ---------------------------------------------------------------------------
# 记忆工具: memory_write + memory_search
# ---------------------------------------------------------------------------



def tool_memory_write(content: str, category: str = "general") -> str:
    print_tool("memory_write", f"[{category}] {content[:60]}...")
    memory_store = container.get("memory_store")  # 从依赖注入容器获取 MemoryStore 实例
    return memory_store.write_memory(content, category)


def tool_memory_search(query: str, top_k: int = 5) -> str:
    print_tool("memory_search", query)
    memory_store = container.get("memory_store")  # 从依赖注入容器获取 MemoryStore 实例
    results = memory_store.hybrid_search(query, top_k)
    if not results:
        return "No relevant memories found."
    return "\n".join(f"[{r['path']}] (score: {r['score']}) {r['snippet']}" for r in results)


# ---------------------------------------------------------------------------
# 工具定义: Schema + Handler
# ---------------------------------------------------------------------------
# 工具 schema 设计说明:
#
# 每个章节 (s02, s06 等) 为了教学清晰度定义了自己的工具集.
# 在生产环境中, 工具 schema 会从共享注册表继承/组合.
#
# s06 中的工具 (memory_write, memory_search) 是对 s02 工具
# (bash, read_file, write_file, edit_file) 的补充 -- 而非替代.
# 完整的 agent 会将两组工具合并为一个列表传递给 LLM.

TOOLS = [
    {
        "name": "memory_write",
        "description": (
            "Save an important fact or observation to long-term memory. "
            "Use when you learn something worth remembering about the user or context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact or observation to remember."},
                "category": {"type": "string", "description": "Category: preference, fact, context, etc."},
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_search",
        "description": "Search stored memories for relevant information, ranked by similarity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "top_k": {"type": "integer", "description": "Max results. Default: 5."},
            },
            "required": ["query"],
        },
    },
]

TOOL_HANDLERS: dict[str, Any] = {
    "memory_write": tool_memory_write,
    "memory_search": tool_memory_search,
}
