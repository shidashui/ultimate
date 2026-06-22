"""Provider factory — 根据配置返回合适的 BaseProvider 实例。"""

from agentd.providers.base import BaseProvider, Response, ContentBlock


def get_provider(config: dict) -> BaseProvider:
    """根据 config 的 model 段返回对应的 provider 实例。

    当前仅支持 Anthropic 兼容协议；后续可扩展 OpenAI、Ollama 等。
    """
    from agentd.providers.anthropic import AnthropicProvider
    return AnthropicProvider(
        api_key=config["api_key"],
        base_url=config["base_url"],
        model=config["name"],
    )


__all__ = ["BaseProvider", "Response", "ContentBlock", "get_provider"]
