"""Main LLM client."""

from collections.abc import Iterator

from .config import Config
from .models import Message, Response, StreamChunk


class LLM:
    """Unified LLM client supporting multiple providers."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        config: Config | None = None,
        **kwargs,
    ):
        """Initialize LLM client.

        Args:
            provider: Provider name (openai, anthropic, google)
            api_key: API key for the provider
            config: Configuration object
            **kwargs: Additional config parameters
        """
        if config is None:
            config_dict = {"provider": provider or "openai"}
            if api_key:
                config_dict["api_key"] = api_key
            config_dict.update(kwargs)
            config = Config(**config_dict)

        self.config = config
        self._provider = self._init_provider()

    # Maps provider name to (module, class_name) for lazy import
    _PROVIDER_MAP = {
        "openai": ("openai", "OpenAIProvider"),
        "anthropic": ("anthropic", "AnthropicProvider"),
        "google": ("google", "GoogleProvider"),
        "azure": ("azure", "AzureOpenAIProvider"),
        "groq": ("groq", "GroqProvider"),
        "mistral": ("mistral", "MistralProvider"),
        "openrouter": ("openrouter", "OpenRouterProvider"),
        "bedrock": ("bedrock", "BedrockProvider"),
        "xai": ("xai", "XAIProvider"),
        "cerebras": ("cerebras", "CerebrasProvider"),
        "cohere": ("cohere", "CohereProvider"),
        "perplexity": ("perplexity", "PerplexityProvider"),
        "deepseek": ("deepseek", "DeepSeekProvider"),
        "together": ("together", "TogetherProvider"),
    }

    def _init_provider(self):
        """Initialize the provider client."""
        entry = self._PROVIDER_MAP.get(self.config.provider)
        if entry:
            module_name, class_name = entry
            import importlib

            mod = importlib.import_module(f".providers.{module_name}", package="pig_llm")
            provider_class = getattr(mod, class_name)
            return provider_class(self.config)

        # Unknown provider → OpenAI-compatible with base_url
        if not self.config.base_url:
            raise ValueError(
                f"Unknown provider '{self.config.provider}'. "
                f"Provide base_url for OpenAI-compatible custom providers."
            )
        from .providers.openai import OpenAIProvider

        return OpenAIProvider(self.config)

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion.

        Args:
            prompt: User prompt
            system: Optional system message
            **kwargs: Additional parameters

        Returns:
            Response object with content and metadata
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        return self._provider.complete(
            messages=messages,
            model=kwargs.get("model", self.config.model),
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            **kwargs,
        )

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """Stream a completion.

        Args:
            prompt: User prompt
            system: Optional system message
            **kwargs: Additional parameters

        Yields:
            StreamChunk objects with content
        """
        messages = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=prompt))

        yield from self._provider.stream(
            messages=messages,
            model=kwargs.get("model", self.config.model),
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            **kwargs,
        )

    def chat(
        self,
        messages: list[Message],
        **kwargs,
    ) -> Response:
        """Generate a chat completion with full message history.

        Args:
            messages: List of Message objects
            **kwargs: Additional parameters (tools, etc.)

        Returns:
            Response object with content and metadata
        """
        model = kwargs.pop("model", self.config.model)
        temperature = kwargs.pop("temperature", self.config.temperature)
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)

        return self._provider.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
