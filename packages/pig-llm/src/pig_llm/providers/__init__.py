"""Provider implementations."""

from ._base import Provider

# Import providers with graceful fallback for missing dependencies.
# Each provider's SDK is optional — only the ones you use need to be installed.

def _try_import(name, module, attr):
    try:
        mod = __import__(f"pig_llm.providers.{module}", fromlist=[attr])
        return getattr(mod, attr)
    except (ImportError, ModuleNotFoundError):
        return None

OpenAIProvider = _try_import("openai", "openai", "OpenAIProvider")
AnthropicProvider = _try_import("anthropic", "anthropic", "AnthropicProvider")
GoogleProvider = _try_import("google", "google", "GoogleProvider")
AzureOpenAIProvider = _try_import("azure", "azure", "AzureOpenAIProvider")
GroqProvider = _try_import("groq", "groq", "GroqProvider")
MistralProvider = _try_import("mistral", "mistral", "MistralProvider")
OpenRouterProvider = _try_import("openrouter", "openrouter", "OpenRouterProvider")
BedrockProvider = _try_import("bedrock", "bedrock", "BedrockProvider")
XAIProvider = _try_import("xai", "xai", "XAIProvider")
CerebrasProvider = _try_import("cerebras", "cerebras", "CerebrasProvider")
CohereProvider = _try_import("cohere", "cohere", "CohereProvider")
PerplexityProvider = _try_import("perplexity", "perplexity", "PerplexityProvider")
DeepSeekProvider = _try_import("deepseek", "deepseek", "DeepSeekProvider")
TogetherProvider = _try_import("together", "together", "TogetherProvider")

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
