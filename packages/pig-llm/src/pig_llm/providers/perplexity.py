"""Perplexity provider implementation (online search-enabled LLM)."""

from typing import AsyncIterator, Iterator, Optional

import openai

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class PerplexityProvider(Provider):
    """Perplexity provider implementation.
    
    Perplexity uses OpenAI-compatible API with online search capabilities.
    """

    def __init__(self, config: Config):
        """Initialize Perplexity provider."""
        self.config = config
        base_url = config.base_url or "https://api.perplexity.ai"
        
        self.client = openai.OpenAI(
            api_key=config.api_key,
            base_url=base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to Perplexity format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Generate a completion with online search."""
        response = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        # Perplexity includes citations in metadata
        metadata = {"id": response.id}
        if hasattr(response, "citations"):
            metadata["citations"] = response.citations

        return Response(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            metadata=metadata,
        )

    def stream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """Stream a completion with online search."""
        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        for chunk in stream:
            choice = chunk.choices[0]
            if choice.delta.content:
                metadata = {"id": chunk.id}
                # Include citations if available
                if hasattr(chunk, "citations"):
                    metadata["citations"] = chunk.citations
                
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                    metadata=metadata,
                )

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Async generate a completion with online search."""
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        # Perplexity includes citations in metadata
        metadata = {"id": response.id}
        if hasattr(response, "citations"):
            metadata["citations"] = response.citations

        return Response(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            metadata=metadata,
        )

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion with online search."""
        stream = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            choice = chunk.choices[0]
            if choice.delta.content:
                metadata = {"id": chunk.id}
                # Include citations if available
                if hasattr(chunk, "citations"):
                    metadata["citations"] = chunk.citations
                
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                    metadata=metadata,
                )
