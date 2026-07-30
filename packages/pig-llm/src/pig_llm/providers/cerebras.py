"""Cerebras provider implementation (ultra-fast inference)."""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import openai

from ..compat import (
    OPENAI_COMPAT,
    apply_prompt_cache,
    apply_request_headers,
    apply_thinking_level,
    astream_openai_tool_aware,
    build_token_limit_param,
    extract_openai_usage,
    normalize_messages,
    stream_openai_tool_aware,
)
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class CerebrasProvider(Provider):
    """Cerebras provider implementation.

    Cerebras uses OpenAI-compatible API for ultra-fast inference.
    """

    def __init__(self, config: Config):
        """Initialize Cerebras provider."""
        self.config = config
        base_url = config.base_url or "https://api.cerebras.ai/v1"

        self.client: Any = openai.OpenAI(
            api_key=config.api_key,
            base_url=base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client: Any = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert internal messages to Cerebras format."""
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
    def _extract_tool_calls(message: Any) -> list[dict[str, Any]] | None:
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
        **kwargs: Any,
    ) -> Response:
        """Generate a completion."""
        kwargs = apply_thinking_level(kwargs, OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=True,
        )
        response = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENAI_COMPAT,
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
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Stream a completion."""
        kwargs = apply_thinking_level(kwargs, OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=True,
        )
        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENAI_COMPAT,
            ),
            **kwargs,
        )

        yield from stream_openai_tool_aware(stream)

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Response:
        """Async generate a completion."""
        kwargs = apply_thinking_level(kwargs, OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=True,
        )
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENAI_COMPAT,
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
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        kwargs = apply_thinking_level(kwargs, OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=True,
        )
        stream = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENAI_COMPAT,
            ),
            **kwargs,
        )

        async for sc in astream_openai_tool_aware(stream):
            yield sc
