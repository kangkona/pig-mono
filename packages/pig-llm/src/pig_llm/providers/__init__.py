"""Provider implementations, imported only when explicitly requested."""

import importlib
from typing import Any

from .._extras import missing_provider_dependency, provider_sdk_is_available
from ._base import Provider

_PROVIDER_EXPORTS = {
    "AnthropicProvider": ("anthropic", "anthropic"),
    "AzureOpenAIProvider": ("azure", "azure"),
    "BedrockProvider": ("bedrock", "bedrock"),
    "CerebrasProvider": ("cerebras", "cerebras"),
    "CohereProvider": ("cohere", "cohere"),
    "DeepSeekProvider": ("deepseek", "deepseek"),
    "GoogleProvider": ("google", "google"),
    "GroqProvider": ("groq", "groq"),
    "MistralProvider": ("mistral", "mistral"),
    "OpenAIProvider": ("openai", "openai"),
    "OpenRouterProvider": ("openrouter", "openrouter"),
    "PerplexityProvider": ("perplexity", "perplexity"),
    "TogetherProvider": ("together", "together"),
    "XAIProvider": ("xai", "xai"),
}


def __getattr__(name: str) -> Any:
    """Load one provider implementation without importing unrelated SDKs."""
    provider_export = _PROVIDER_EXPORTS.get(name)
    if provider_export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, provider_id = provider_export
    if not provider_sdk_is_available(provider_id):
        raise missing_provider_dependency(provider_id)
    module = importlib.import_module(f".{module_name}", package=__name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose lazy provider classes to introspection and documentation tools."""
    return sorted({*globals(), *_PROVIDER_EXPORTS})


__all__ = [
    "Provider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GoogleProvider",
    "AzureOpenAIProvider",
    "GroqProvider",
    "MistralProvider",
    "OpenRouterProvider",
    "BedrockProvider",
    "XAIProvider",
    "CerebrasProvider",
    "CohereProvider",
    "PerplexityProvider",
    "DeepSeekProvider",
    "TogetherProvider",
]
