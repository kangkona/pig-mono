"""OpenAI provider implementation."""

from collections.abc import AsyncIterator, Iterator

import openai

from ..compat import (
    DEEPSEEK_COMPAT,
    MOONSHOT_COMPAT,
    OPENAI_COMPAT,
    OPENCODE_GO_KIMI_COMPAT,
    OPENCODE_ZEN_GROK_BUILD_COMPAT,
    OPENROUTER_COMPAT,
    QWEN_CHAT_TEMPLATE_COMPAT,
    QWEN_COMPAT,
    STRING_THINKING_COMPAT,
    TOGETHER_COMPAT,
    ZAI_COMPAT,
    apply_prompt_cache,
    apply_request_headers,
    apply_session_affinity_headers,
    apply_thinking_level,
    build_token_limit_param,
    extract_openai_usage,
    normalize_messages,
)
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class OpenAIProvider(Provider):
    """OpenAI provider implementation."""

    _COMPAT_MODE_MAP = {
        "openai": OPENAI_COMPAT,
        "openrouter": OPENROUTER_COMPAT,
        "deepseek": DEEPSEEK_COMPAT,
        "moonshot": MOONSHOT_COMPAT,
        "together": TOGETHER_COMPAT,
        "qwen": QWEN_COMPAT,
        "qwen-chat-template": QWEN_CHAT_TEMPLATE_COMPAT,
        "zai": ZAI_COMPAT,
        "string-thinking": STRING_THINKING_COMPAT,
    }

    def _compat(self, model: str | None = None):
        base_url = (self.config.base_url or "").lower()
        model_name = (model or self.config.model or "").lower()
        compat_mode = (self.config.compat_mode or "").lower()
        if compat_mode in self._COMPAT_MODE_MAP:
            return self._COMPAT_MODE_MAP[compat_mode]
        if "openrouter.ai" in base_url:
            return OPENROUTER_COMPAT
        if "api.moonshot.ai" in base_url or "api.moonshot.cn" in base_url:
            return MOONSHOT_COMPAT
        if "opencode.ai/zen/go" in base_url and model_name in {
            "kimi-k2.6",
            "deepseek-v4-flash",
            "deepseek-v4-pro",
        }:
            return OPENCODE_GO_KIMI_COMPAT if model_name == "kimi-k2.6" else DEEPSEEK_COMPAT
        if "opencode.ai/zen/go" in base_url and model_name == "qwen3.6-plus":
            return QWEN_COMPAT
        if "opencode.ai/zen" in base_url and model_name == "kimi-k2.6":
            return OPENCODE_GO_KIMI_COMPAT
        if "opencode.ai/zen" in base_url and model_name in {"deepseek-v4-flash", "deepseek-v4-pro"}:
            return DEEPSEEK_COMPAT
        if "opencode.ai/zen" in base_url and model_name == "grok-build-0.1":
            return OPENCODE_ZEN_GROK_BUILD_COMPAT
        if "dashscope.aliyuncs.com" in base_url:
            return QWEN_COMPAT
        if "api.z.ai" in base_url:
            return ZAI_COMPAT
        return OPENAI_COMPAT

    def __init__(self, config: Config):
        """Initialize OpenAI provider."""
        self.config = config
        self.client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client = openai.AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to OpenAI format."""
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

    @staticmethod
    def _token_limit_param(max_tokens: int | None, compat=OPENAI_COMPAT) -> dict[str, int]:
        """Build token limit parameters for current OpenAI-compatible chat models."""
        return build_token_limit_param(
            max_tokens,
            param_name=compat.token_limit_field,
            compat=compat,
        )

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        compat = self._compat(model)
        kwargs["model"] = model
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            compat,
            supports_developer_role=compat is OPENAI_COMPAT,
        )
        response = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **self._token_limit_param(max_tokens, compat),
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
        compat = self._compat(model)
        kwargs["model"] = model
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            compat,
            supports_developer_role=compat is OPENAI_COMPAT,
        )
        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            stream=True,
            **self._token_limit_param(max_tokens, compat),
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
        compat = self._compat(model)
        kwargs["model"] = model
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            compat,
            supports_developer_role=compat is OPENAI_COMPAT,
        )
        response = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            **self._token_limit_param(max_tokens, compat),
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
        compat = self._compat(model)
        kwargs["model"] = model
        kwargs = apply_thinking_level(kwargs, compat)
        kwargs.pop("model", None)
        kwargs = apply_prompt_cache(kwargs, compat)
        kwargs = apply_session_affinity_headers(kwargs, compat)
        kwargs = apply_request_headers(kwargs)
        normalized_messages = normalize_messages(
            messages,
            compat,
            supports_developer_role=compat is OPENAI_COMPAT,
        )
        stream = await self.async_client.chat.completions.create(
            model=model,
            messages=self._convert_messages(normalized_messages),
            temperature=temperature,
            stream=True,
            **self._token_limit_param(max_tokens, compat),
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
