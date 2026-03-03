"""DeepSeek provider implementation (Chinese LLM)."""

from collections.abc import AsyncIterator, Iterator

import openai

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class DeepSeekProvider(Provider):
    """DeepSeek provider implementation.

    DeepSeek uses OpenAI-compatible API, optimized for Chinese and code.
    """

    def __init__(self, config: Config):
        """Initialize DeepSeek provider."""
        self.config = config
        base_url = config.base_url or "https://api.deepseek.com"

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
        """Convert internal messages to DeepSeek format."""
        result = []
        for msg in messages:
            if msg.role == "assistant" and msg.metadata and "tool_calls" in msg.metadata:
                result.append(
                    {
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": msg.metadata["tool_calls"],
                    }
                )
            elif msg.role == "tool" and msg.metadata:
                result.append(
                    {
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": msg.metadata.get("tool_call_id", ""),
                    }
                )
            else:
                result.append({"role": msg.role, "content": msg.content})
        return result

    @staticmethod
    def _extract_tool_calls(message) -> list[dict] | None:
        """Extract tool_calls from OpenAI response message."""
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return None
        return [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
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

        return Response(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            tool_calls=self._extract_tool_calls(choice.message),
            metadata={"id": response.id},
        )

    def stream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
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
        max_tokens: int | None = None,
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
            tool_calls=self._extract_tool_calls(choice.message),
            metadata={"id": response.id},
        )

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
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
