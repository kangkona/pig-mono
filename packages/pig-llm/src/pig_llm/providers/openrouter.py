"""OpenRouter provider (aggregates multiple providers)."""

from collections.abc import AsyncIterator, Iterator

import openai

from ..compat import (
    OPENROUTER_COMPAT,
    apply_request_headers,
    apply_thinking_level,
    build_token_limit_param,
    extract_openai_usage,
)
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class OpenRouterProvider(Provider):
    """OpenRouter provider (access multiple models via one API)."""

    def __init__(self, config: Config):
        """Initialize OpenRouter provider.

        OpenRouter uses OpenAI-compatible API.
        """
        self.config = config

        # OpenRouter uses OpenAI client with custom base URL
        self.client = openai.OpenAI(
            api_key=config.api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

        self.async_client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to OpenRouter/OpenAI format."""
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
        kwargs = apply_thinking_level(kwargs, OPENROUTER_COMPAT)
        kwargs = apply_request_headers(kwargs)
        response = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENROUTER_COMPAT,
            ),
            **kwargs,
        )

        choice = response.choices[0]
        usage = extract_openai_usage(response)

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
        kwargs = apply_thinking_level(kwargs, OPENROUTER_COMPAT)
        kwargs = apply_request_headers(kwargs)
        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            stream=True,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENROUTER_COMPAT,
            ),
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
        kwargs = apply_thinking_level(kwargs, OPENROUTER_COMPAT)
        kwargs = apply_request_headers(kwargs)
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENROUTER_COMPAT,
            ),
            **kwargs,
        )

        choice = response.choices[0]
        usage = extract_openai_usage(response)

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
        kwargs = apply_thinking_level(kwargs, OPENROUTER_COMPAT)
        kwargs = apply_request_headers(kwargs)
        stream = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            stream=True,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENROUTER_COMPAT,
            ),
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
