"""AnthropicProvider — Anthropic SDK 的 BaseProvider 实现。"""

import anthropic
from agentd.providers.base import BaseProvider, ContentBlock, Response


class AnthropicProvider(BaseProvider):
    """封装 anthropic.AsyncAnthropic，输出归一化 Response。"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self._model = model
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
        )

    async def chat(
        self,
        messages: list[dict],
        system: str | list,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> Response:
        kwargs.setdefault("max_tokens", 8096)
        kwargs["model"] = self._model
        kwargs["system"] = system
        kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = tools

        result = await self._client.messages.create(**kwargs)

        # 归一化 SDK 响应
        content: list[ContentBlock] = []
        for block in result.content:
            if hasattr(block, "text"):
                content.append(ContentBlock(
                    type="text",
                    text=block.text,
                ))
            elif block.type == "tool_use":
                content.append(ContentBlock(
                    type="tool_use",
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))

        return Response(
            content=content,
            stop_reason=result.stop_reason,
        )

    def estimate_tokens(self, text: str) -> int:
        try:
            return anthropic.count_tokens(text)
        except Exception:
            return len(text) // 4
