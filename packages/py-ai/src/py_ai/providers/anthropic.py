"""Anthropic provider implementation."""

from typing import AsyncIterator, Iterator, Optional

import anthropic

from ..config import Config
from ..models import Message, Response, StreamChunk
from ..providers import Provider


class AnthropicProvider(Provider):
    """Anthropic (Claude) provider implementation."""

    def __init__(self, config: Config):
        """Initialize Anthropic provider."""
        self.config = config
        self.client = anthropic.Anthropic(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> tuple[Optional[str], list[dict]]:
        """Convert internal messages to Anthropic format.
        
        Returns:
            Tuple of (system_message, messages_list)
        """
        system_message = None
        anthropic_messages = []
        
        for msg in messages:
            if msg.role == "system":
                system_message = msg.content
            else:
                anthropic_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        return system_message, anthropic_messages

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        system, anthropic_messages = self._convert_messages(messages)
        
        response = self.client.messages.create(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )

        # Extract content
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return Response(
            content=content,
            model=response.model,
            usage=usage,
            finish_reason=response.stop_reason,
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
        system, anthropic_messages = self._convert_messages(messages)
        
        with self.client.messages.stream(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        ) as stream:
            for text in stream.text_stream:
                yield StreamChunk(content=text, finish_reason=None)

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Async generate a completion."""
        system, anthropic_messages = self._convert_messages(messages)
        
        response = await self.async_client.messages.create(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return Response(
            content=content,
            model=response.model,
            usage=usage,
            finish_reason=response.stop_reason,
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
        system, anthropic_messages = self._convert_messages(messages)
        
        async with self.async_client.messages.stream(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(content=text, finish_reason=None)
