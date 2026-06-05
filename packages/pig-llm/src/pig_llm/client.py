"""Main LLM client."""

from collections.abc import AsyncIterator, Iterator

from .config import Config
from .models import Message, Response, StreamChunk


class LLM:
    """Unified LLM client supporting multiple providers."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        config: Config | None = None,
        enable_web_search: bool = False,
        web_search_max_uses: int = 5,
        **kwargs,
    ):
        """Initialize LLM client.

        Args:
            provider: Provider name (openai, anthropic, google)
            api_key: API key for the provider
            config: Configuration object
            enable_web_search: Enable the model provider's native server-side web
                search. Provider-neutral intent — only forwarded to providers that
                support it (currently Anthropic), which translate it into their
                native tool spec.
            web_search_max_uses: Max distinct searches per request (Anthropic).
            **kwargs: Additional config parameters
        """
        if config is None:
            config_dict = {"provider": provider or "openai"}
            if api_key:
                config_dict["api_key"] = api_key
            config_dict.update(kwargs)
            config = Config(**config_dict)

        if not config.model:
            raise ValueError(
                f"No model specified for provider '{config.provider}'. "
                "Pass --model / -m or set the model in your config."
            )
        self.config = config
        self.enable_web_search = enable_web_search
        self.web_search_max_uses = web_search_max_uses
        self._provider = self._init_provider()

    def _inject_web_search(self, kwargs: dict) -> None:
        """Add the native web-search intent for providers that support it.

        Gated by provider so the control flags never reach an SDK that would
        reject them as unknown kwargs. The provider pops the flags and emits its
        own native server-tool spec.
        """
        if self.enable_web_search and self.config.provider == "anthropic":
            kwargs.setdefault("enable_web_search", True)
            kwargs.setdefault("web_search_max_uses", self.web_search_max_uses)

    @property
    def model(self) -> str:
        """Return the configured model name (validated at construction time)."""
        return self.config.model  # type: ignore[return-value]

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
            if self.config.provider != "bedrock" and not self.config.api_key:
                raise ValueError(f"No API key for provider: {self.config.provider}")
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

        self._inject_web_search(kwargs)
        return self._provider.complete(
            messages=messages,
            model=kwargs.get("model", self.model),
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

        self._inject_web_search(kwargs)
        yield from self._provider.stream(
            messages=messages,
            model=kwargs.get("model", self.model),
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
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", self.config.temperature)
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)
        self._inject_web_search(kwargs)

        return self._provider.complete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def achat(
        self,
        messages: list[Message],
        **kwargs,
    ) -> Response:
        """Async generate a chat completion with full message history.

        Args:
            messages: List of Message objects
            **kwargs: Additional parameters (tools, etc.)

        Returns:
            Response object with content and metadata
        """
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", self.config.temperature)
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)
        self._inject_web_search(kwargs)

        return await self._provider.acomplete(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def achat_stream(
        self,
        messages: list[Message],
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a chat completion with full message history.

        Args:
            messages: List of Message objects
            **kwargs: Additional parameters (tools, etc.)

        Yields:
            StreamChunk objects with content
        """
        model = kwargs.pop("model", self.model)
        temperature = kwargs.pop("temperature", self.config.temperature)
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)
        self._inject_web_search(kwargs)

        async for chunk in self._provider.astream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        ):
            yield chunk
