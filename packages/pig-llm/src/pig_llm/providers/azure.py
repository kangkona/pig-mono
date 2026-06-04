"""Azure OpenAI provider implementation."""

from collections.abc import AsyncIterator, Iterator

import openai

from ..compat import (
    AZURE_OPENAI_COMPAT,
    apply_prompt_cache,
    apply_request_headers,
    apply_session_affinity_headers,
    apply_thinking_level,
    astream_openai_tool_aware,
    build_token_limit_param,
    iter_openai_stream_choices,
    normalize_messages,
)
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


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
        kwargs = apply_thinking_level(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            AZURE_OPENAI_COMPAT,
            supports_developer_role=True,
        )
        response = self.client.chat.completions.create(
            model=model,  # This is the deployment name in Azure
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=AZURE_OPENAI_COMPAT,
            ),
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
        kwargs = apply_thinking_level(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            AZURE_OPENAI_COMPAT,
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
                compat=AZURE_OPENAI_COMPAT,
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
        kwargs = apply_thinking_level(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            AZURE_OPENAI_COMPAT,
            supports_developer_role=True,
        )
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **build_token_limit_param(
                max_tokens,
                param_name="max_tokens",
                compat=AZURE_OPENAI_COMPAT,
            ),
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
        kwargs = apply_thinking_level(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_prompt_cache(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_session_affinity_headers(kwargs, AZURE_OPENAI_COMPAT)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            AZURE_OPENAI_COMPAT,
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
                compat=AZURE_OPENAI_COMPAT,
            ),
            **kwargs,
        )

        async for sc in astream_openai_tool_aware(stream):
            yield sc
