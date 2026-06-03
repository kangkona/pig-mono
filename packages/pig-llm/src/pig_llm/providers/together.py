"""Together AI provider implementation (open-source models)."""

from collections.abc import AsyncIterator, Iterator

import openai

from ..compat import (
    TOGETHER_COMPAT,
    TOGETHER_OPENAI_REASONING_COMPAT,
    aiter_openai_stream_choices,
    apply_prompt_cache,
    apply_request_headers,
    apply_session_affinity_headers,
    apply_thinking_level,
    build_token_limit_param,
    extract_openai_usage,
    iter_openai_stream_choices,
    normalize_messages,
)
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class TogetherProvider(Provider):
    """Together AI provider implementation.

    Together AI uses OpenAI-compatible API for open-source models.
    """

    @staticmethod
    def _compat(model: str):
        if model.lower() in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
            return TOGETHER_OPENAI_REASONING_COMPAT
        return TOGETHER_COMPAT

    def __init__(self, config: Config):
        """Initialize Together AI provider."""
        self.config = config
        base_url = config.base_url or "https://api.together.xyz/v1"

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
        """Convert internal messages to Together AI format."""
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
        kwargs["model"] = model
        compat = self._compat(model)
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(messages, compat)
        response = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=compat,
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
        kwargs["model"] = model
        compat = self._compat(model)
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(messages, compat)
        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            stream=True,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=compat,
            ),
            **kwargs,
        )

        for chunk, choice in iter_openai_stream_choices(stream):
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
        kwargs["model"] = model
        compat = self._compat(model)
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(messages, compat)
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=compat,
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
        kwargs["model"] = model
        compat = self._compat(model)
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(messages, compat)
        stream = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            stream=True,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=compat,
            ),
            **kwargs,
        )

        async for chunk, choice in aiter_openai_stream_choices(stream):
            if choice.delta.content:
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                    metadata={"id": chunk.id},
                )
