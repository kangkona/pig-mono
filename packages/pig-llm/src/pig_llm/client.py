"""Main LLM client."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any, cast

from .config import Config
from .models import Message, Response, StreamChunk
from .runtime import ModelRuntime, get_default_runtime

if TYPE_CHECKING:
    from .providers._base import Provider


class LLM:
    """Unified LLM client supporting multiple providers."""

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        config: Config | None = None,
        enable_web_search: bool = False,
        web_search_max_uses: int = 5,
        runtime: ModelRuntime | None = None,
        **kwargs: Any,
    ) -> None:
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
            runtime: Explicit provider/model runtime. Defaults to the built-in
                process runtime for backwards compatibility.
            **kwargs: Additional config parameters
        """
        if config is None:
            config_dict: dict[str, Any] = {"provider": provider or "openai"}
            if api_key:
                config_dict["api_key"] = api_key
            config_dict.update(kwargs)
            config = Config(**config_dict)

        self.config = config
        self.runtime = runtime or get_default_runtime()
        self.enable_web_search = enable_web_search
        self.web_search_max_uses = web_search_max_uses
        self._provider = self._init_provider()
        if not config.model:
            raise ValueError(
                f"No model specified for provider '{config.provider}'. "
                "Pass --model / -m or set the model in your config."
            )

    def _inject_web_search(self, kwargs: dict[str, Any]) -> None:
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
        return cast(str, self.config.model)

    def _init_provider(self) -> Provider:
        """Initialize the provider client."""
        return self.runtime.create_provider(self.config)

    def with_profile(self, *, api_key: str, model: str | None = None) -> LLM:
        """Create an equivalent client bound to an explicitly selected credential.

        Resilience code uses this immutable clone operation so a profile-rotation
        event always corresponds to a real provider client rebuilt with the new
        key.  The original client and its frozen configuration remain unchanged.
        """
        config = self.config.model_copy(
            update={
                "api_key": api_key,
                "model": model or self.config.model,
            }
        )
        return LLM(
            config=config,
            runtime=self.runtime,
            enable_web_search=self.enable_web_search,
            web_search_max_uses=self.web_search_max_uses,
        )

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        **kwargs: Any,
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
        **kwargs: Any,
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
        **kwargs: Any,
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
        **kwargs: Any,
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
        **kwargs: Any,
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
