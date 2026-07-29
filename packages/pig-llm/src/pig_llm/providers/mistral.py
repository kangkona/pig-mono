"""Mistral AI provider implementation."""

from collections.abc import AsyncIterator, Iterator
from importlib import import_module
from typing import Any

try:
    ChatMessage: Any = import_module("mistralai.models.chat_completion").ChatMessage
except ImportError:
    # mistralai 1.x accepts the same role/content mapping but removed ChatMessage.
    ChatMessage = dict

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class MistralProvider(Provider):
    """Mistral AI provider implementation."""

    def __init__(self, config: Config):
        """Initialize Mistral provider."""
        self.config = config
        mistral_module = import_module("mistralai")
        client_module = import_module("mistralai.client")
        modern_client = getattr(mistral_module, "Mistral", None) or getattr(
            client_module, "Mistral", None
        )
        if modern_client is not None:
            self.client: Any = modern_client(api_key=config.api_key)
            self.async_client: Any = self.client
            self._uses_modern_client = True
        else:
            legacy_client = vars(client_module)["MistralClient"]
            legacy_async_client = vars(import_module("mistralai.async_client"))[
                "MistralAsyncClient"
            ]
            self.client = legacy_client(api_key=config.api_key)
            self.async_client = legacy_async_client(api_key=config.api_key)
            self._uses_modern_client = False

    @staticmethod
    def _stream_payload(event: Any) -> Any:
        """Unwrap the event envelope introduced by mistralai 1.x."""
        return getattr(event, "data", event)

    def _convert_messages(self, messages: list[Message]) -> list[Any]:
        """Convert internal messages to Mistral format."""
        return [ChatMessage(role=msg.role, content=msg.content) for msg in messages]

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Response:
        """Generate a completion."""
        request = {
            "model": model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if self._uses_modern_client:
            response = self.client.chat.complete(**request)
        else:
            response = self.client.chat(**request)

        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        return Response(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            metadata={"id": response.id},
        )

    def stream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Stream a completion."""
        request = {
            "model": model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if self._uses_modern_client:
            stream = self.client.chat.stream(**request)
        else:
            stream = self.client.chat_stream(**request)

        for event in stream:
            chunk = self._stream_payload(event)
            choice = chunk.choices[0]
            if choice.delta.content:
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                )

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Response:
        """Async generate a completion."""
        request = {
            "model": model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if self._uses_modern_client:
            response = await self.async_client.chat.complete_async(**request)
        else:
            response = await self.async_client.chat(**request)

        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        return Response(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            metadata={"id": response.id},
        )

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        request = {
            "model": model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if self._uses_modern_client:
            stream = await self.async_client.chat.stream_async(**request)
        else:
            stream = await self.async_client.chat_stream(**request)

        usage = None
        async for event in stream:
            chunk = self._stream_payload(event)
            choice = chunk.choices[0]
            if choice.delta.content:
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                )
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage:
                usage = {
                    "input_tokens": int(getattr(chunk_usage, "prompt_tokens", 0) or 0),
                    "output_tokens": int(getattr(chunk_usage, "completion_tokens", 0) or 0),
                    "total_tokens": int(getattr(chunk_usage, "total_tokens", 0) or 0),
                }
        if usage:
            yield StreamChunk(content="", usage=usage)
