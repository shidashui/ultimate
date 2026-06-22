"""BaseProvider — LLM API 提供者抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ContentBlock:
    """归一化的响应内容块。"""
    type: str                       # "text" | "tool_use"
    text: str = ""                  # type="text" 时有值
    id: str = ""                    # type="tool_use" 时有值
    name: str = ""                  # type="tool_use" 时有值
    input: dict = field(default_factory=dict)  # type="tool_use" 时有值


@dataclass
class Response:
    """归一化的 LLM 响应。"""
    content: list[ContentBlock]
    stop_reason: str                # "end_turn" | "tool_use" | "max_tokens"


class BaseProvider(ABC):
    """LLM API 提供者抽象基类。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        system: str | list,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Response:
        """发送消息并获取完整响应。"""
        ...

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数量。"""
        ...
