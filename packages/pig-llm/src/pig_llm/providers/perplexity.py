"""Perplexity provider implementation (online search-enabled LLM)."""

from collections.abc import AsyncIterator, Iterator

import openai

from ..compat import (
    OPENAI_COMPAT,
    _OpenAIToolCallAccumulator,
    aiter_openai_stream_choices,
    apply_prompt_cache,
    apply_request_headers,
    apply_thinking_level,
    build_token_limit_param,
    iter_openai_stream_choices,
    normalize_messages,
)
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
        """Generate a completion with online search."""
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
            tool_calls=self._extract_tool_calls(choice.message),
            metadata=metadata,
        )

    def stream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """Stream a completion with online search."""
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
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENAI_COMPAT,
            ),
            **kwargs,
        )

        for chunk, choice in iter_openai_stream_choices(stream):
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
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Async generate a completion with online search."""
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
            tool_calls=self._extract_tool_calls(choice.message),
            metadata=metadata,
        )

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion with online search."""
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
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=OPENAI_COMPAT,
            ),
            **kwargs,
        )

        accumulator = _OpenAIToolCallAccumulator()
        async for chunk, choice in aiter_openai_stream_choices(stream):
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
            accumulator.add(choice)
        tool_calls = accumulator.finish()
        if tool_calls:
            yield StreamChunk(content="", tool_calls=tool_calls)
