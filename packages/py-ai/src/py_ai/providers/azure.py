"""Azure OpenAI provider implementation."""

from typing import AsyncIterator, Iterator, Optional

import openai

from ..config import Config
from ..models import Message, Response, StreamChunk
from ..providers import Provider


class AzureOpenAIProvider(Provider):
    """Azure OpenAI provider implementation."""

    def __init__(self, config: Config):
        """Initialize Azure OpenAI provider.
        
        Requires:
        - config.api_key: Azure API key
        - config.base_url: Azure endpoint (e.g., https://xxx.openai.azure.com/)
        - Environment variable AZURE_OPENAI_API_VERSION (default: 2024-02-15-preview)
        """
        self.config = config
        
        import os
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        
        self.client = openai.AzureOpenAI(
            api_key=config.api_key,
            azure_endpoint=config.base_url,
            api_version=api_version,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        
        self.async_client = openai.AsyncAzureOpenAI(
            api_key=config.api_key,
            azure_endpoint=config.base_url,
            api_version=api_version,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to Azure OpenAI format."""
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        response = self.client.chat.completions.create(
            model=model,  # This is the deployment name in Azure
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
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                    metadata={"id": chunk.id},
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
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                    metadata={"id": chunk.id},
                )
