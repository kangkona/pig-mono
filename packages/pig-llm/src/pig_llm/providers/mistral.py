"""Mistral AI provider implementation."""

from typing import AsyncIterator, Iterator, Optional

from mistralai.client import MistralClient
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class MistralProvider(Provider):
    """Mistral AI provider implementation."""

    def __init__(self, config: Config):
        """Initialize Mistral provider."""
        self.config = config
        self.client = MistralClient(api_key=config.api_key)
        self.async_client = MistralAsyncClient(api_key=config.api_key)

    def _convert_messages(self, messages: list[Message]) -> list[ChatMessage]:
        """Convert internal messages to Mistral format."""
        return [
            ChatMessage(role=msg.role, content=msg.content) for msg in messages
        ]

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        response = self.client.chat(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens
            if response.usage
            else 0,
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
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """Stream a completion."""
        stream = self.client.chat_stream(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        for chunk in stream:
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
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Async generate a completion."""
        response = await self.async_client.chat(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens
            if response.usage
            else 0,
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
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        stream = await self.async_client.chat_stream(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        async for chunk in stream:
            choice = chunk.choices[0]
            if choice.delta.content:
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                )
