"""Provider factory — 根据 Config 对象返回合适的 BaseProvider 实例。"""

from agentd.providers.base import BaseProvider, Response, ContentBlock


def get_provider(config) -> BaseProvider:
    """根据 config.model 返回匹配的 provider 实例。

    config: Config 对象（来自 config.configs）。

    查找逻辑：
    1. 读取 config.model.default → 当前 provider name
    2. 在 config.model.providers 中匹配 name
    3. 使用已注入的 api_key 构造对应的 Provider

    当前仅支持 Anthropic 兼容协议；后续可扩展 OpenAI、Ollama 等。
    """
    from agentd.providers.anthropic import AnthropicProvider

    default_name = config.model.default
    provider_cfg = None
    for p in config.model.providers:
        if p.name == default_name:
            provider_cfg = p
            break

    if provider_cfg is None:
        raise ValueError(
            f"Default provider '{default_name}' not found in providers list. "
            f"Available: {[p.name for p in config.model.providers]}"
        )

    # Dispatch to appropriate provider class
    # Future: check provider_cfg.type or name prefix for OpenAI/Ollama
    return AnthropicProvider(
        api_key=provider_cfg.api_key,
        base_url=provider_cfg.base_url,
        model=provider_cfg.model,
    )


__all__ = ["BaseProvider", "Response", "ContentBlock", "get_provider"]
