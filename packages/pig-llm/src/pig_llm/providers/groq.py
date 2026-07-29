"""Groq provider implementation (ultra-fast inference)."""

from collections.abc import AsyncIterator, Iterator
from typing import Any

from groq import AsyncGroq, Groq

from ..compat import (
    GROQ_COMPAT,
    apply_prompt_cache,
    apply_request_headers,
    apply_session_affinity_headers,
    apply_thinking_level,
    astream_openai_tool_aware,
    iter_openai_stream_choices,
    normalize_messages,
)
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class GroqProvider(Provider):
    """Groq provider implementation (fast LLM inference)."""

    @staticmethod
    def _apply_reasoning_effort_override(model: str, kwargs: dict[str, Any]) -> dict:
        """Apply known model-specific reasoning-effort overrides."""
        next_kwargs = dict(kwargs)
        if model.lower() == "qwen/qwen3-32b" and next_kwargs.get("reasoning_effort") == "medium":
            next_kwargs["reasoning_effort"] = "default"
        return next_kwargs

    def __init__(self, config: Config):
        """Initialize Groq provider."""
        self.config = config
        self.client: Any = Groq(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client: Any = AsyncGroq(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert internal messages to Groq format."""
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
        kwargs = apply_thinking_level(kwargs, GROQ_COMPAT)
        kwargs = self._apply_reasoning_effort_override(model, kwargs)
        kwargs = apply_prompt_cache(kwargs, GROQ_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, GROQ_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            GROQ_COMPAT,
            supports_developer_role=True,
        )
        response = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
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
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Stream a completion."""
        kwargs = apply_thinking_level(kwargs, GROQ_COMPAT)
        kwargs = self._apply_reasoning_effort_override(model, kwargs)
        kwargs = apply_prompt_cache(kwargs, GROQ_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, GROQ_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            GROQ_COMPAT,
            supports_developer_role=True,
        )
        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
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
        **kwargs: Any,
    ) -> Response:
        """Async generate a completion."""
        kwargs = apply_thinking_level(kwargs, GROQ_COMPAT)
        kwargs = self._apply_reasoning_effort_override(model, kwargs)
        kwargs = apply_prompt_cache(kwargs, GROQ_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, GROQ_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            GROQ_COMPAT,
            supports_developer_role=True,
        )
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
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
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        kwargs = apply_thinking_level(kwargs, GROQ_COMPAT)
        kwargs = self._apply_reasoning_effort_override(model, kwargs)
        kwargs = apply_prompt_cache(kwargs, GROQ_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, GROQ_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            GROQ_COMPAT,
            supports_developer_role=True,
        )
        stream = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )

        async for sc in astream_openai_tool_aware(stream):
            yield sc
