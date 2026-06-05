"""Anthropic provider implementation."""

import json
import os
from collections.abc import AsyncIterator, Iterator

import anthropic

from ..compat import ANTHROPIC_COMPAT, apply_thinking_level, normalize_messages
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class AnthropicProvider(Provider):
    """Anthropic (Claude) provider implementation."""

    @staticmethod
    def _supports_temperature(model: str) -> bool:
        """Claude Opus 4.7+ rejects explicit temperature parameters."""
        model_name = (model or "").lower()
        return "claude-opus-4-7" not in model_name and "claude-opus-4-8" not in model_name

    def __init__(self, config: Config):
        """Initialize Anthropic provider."""
        self.config = config
        # Allow a custom endpoint via config.base_url or ANTHROPIC_BASE_URL.
        base_url = config.base_url or os.environ.get("ANTHROPIC_BASE_URL")
        client_kwargs: dict = {
            "api_key": config.api_key,
            "timeout": config.timeout,
            "max_retries": config.max_retries,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**client_kwargs)
        self.async_client = anthropic.AsyncAnthropic(**client_kwargs)

    def _convert_messages(self, messages: list[Message]) -> tuple[str | None, list[dict]]:
        """Convert internal messages to Anthropic format.

        Returns:
            Tuple of (system_message, messages_list)
        """
        system_message = None
        anthropic_messages = []

        for msg in messages:
            if msg.role == "system":
                system_message = msg.content

            elif msg.role == "assistant" and msg.metadata and "tool_calls" in msg.metadata:
                # Rebuild assistant message with tool_use blocks
                content = []

                # Add text block if present
                if msg.content:
                    content.append({"type": "text", "text": msg.content})

                # Add tool_use blocks
                for tc in msg.metadata["tool_calls"]:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": json.loads(tc["function"]["arguments"]),
                        }
                    )

                anthropic_messages.append({"role": "assistant", "content": content})

            elif msg.role == "tool" and msg.metadata:
                # Convert tool result to tool_result block
                tool_use_id = msg.metadata.get("tool_call_id")
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": msg.content,
                            }
                        ],
                    }
                )

            else:
                # Regular message
                anthropic_messages.append({"role": msg.role, "content": msg.content})

        return system_message, anthropic_messages

    @staticmethod
    def _extract_tool_calls(content_blocks) -> list[dict] | None:
        """Extract tool_use blocks from Anthropic response content."""
        tool_calls = []

        for block in content_blocks:
            if block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input),
                        },
                    }
                )

        return tool_calls if tool_calls else None

    def _convert_tools(self, tools: list[dict] | None) -> list[dict] | None:
        """Convert OpenAI-style tools to Anthropic format."""
        if not tools:
            return None

        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )

        return anthropic_tools if anthropic_tools else None

    def _resolve_tools_with_web_search(self, kwargs: dict) -> list[dict] | None:
        """Build the Anthropic tools list from function tools + optional native search.

        Pops the provider-neutral control flags (``enable_web_search`` /
        ``web_search_max_uses``) so they never reach the SDK, and when enabled
        appends Anthropic's native server-side web search tool. The model invokes
        it server-side; results come back as ``web_search_tool_result`` content
        (not ``tool_use``), so they are never dispatched as local tool calls.
        """
        enable_web = kwargs.pop("enable_web_search", False)
        max_uses = kwargs.pop("web_search_max_uses", 5)
        tools = self._convert_tools(kwargs.get("tools")) or []
        if enable_web:
            tools = list(tools)
            tools.append(
                {"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}
            )
        return tools or None

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        normalized_messages = normalize_messages(messages, ANTHROPIC_COMPAT)
        system, anthropic_messages = self._convert_messages(normalized_messages)

        # Convert tools (+ optional native web search) if present
        kwargs = apply_thinking_level(kwargs, ANTHROPIC_COMPAT)
        tools = self._resolve_tools_with_web_search(kwargs)
        kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
        if tools:
            kwargs["tools"] = tools

        request_kwargs = dict(kwargs)
        if self._supports_temperature(model):
            request_kwargs["temperature"] = temperature

        response = self.client.messages.create(
            model=model,
            messages=anthropic_messages,
            system=system,
            max_tokens=max_tokens or 4096,
            **request_kwargs,
        )

        # Extract text content
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        # Extract tool_calls
        tool_calls = self._extract_tool_calls(response.content)

        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return Response(
            content=content,
            model=response.model,
            usage=usage,
            finish_reason=response.stop_reason,
            tool_calls=tool_calls,
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
        normalized_messages = normalize_messages(messages, ANTHROPIC_COMPAT)
        system, anthropic_messages = self._convert_messages(normalized_messages)
        kwargs = apply_thinking_level(kwargs, ANTHROPIC_COMPAT)
        request_kwargs = dict(kwargs)
        if self._supports_temperature(model):
            request_kwargs["temperature"] = temperature

        with self.client.messages.stream(
            model=model,
            messages=anthropic_messages,
            system=system,
            max_tokens=max_tokens or 4096,
            **request_kwargs,
        ) as stream:
            for text in stream.text_stream:
                yield StreamChunk(content=text, finish_reason=None)

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Async generate a completion."""
        normalized_messages = normalize_messages(messages, ANTHROPIC_COMPAT)
        system, anthropic_messages = self._convert_messages(normalized_messages)

        # Convert tools (+ optional native web search) if present
        kwargs = apply_thinking_level(kwargs, ANTHROPIC_COMPAT)
        tools = self._resolve_tools_with_web_search(kwargs)
        kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
        if tools:
            kwargs["tools"] = tools

        request_kwargs = dict(kwargs)
        if self._supports_temperature(model):
            request_kwargs["temperature"] = temperature

        response = await self.async_client.messages.create(
            model=model,
            messages=anthropic_messages,
            system=system,
            max_tokens=max_tokens or 4096,
            **request_kwargs,
        )

        # Extract text content
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        # Extract tool_calls
        tool_calls = self._extract_tool_calls(response.content)

        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

        return Response(
            content=content,
            model=response.model,
            usage=usage,
            finish_reason=response.stop_reason,
            tool_calls=tool_calls,
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
        normalized_messages = normalize_messages(messages, ANTHROPIC_COMPAT)
        system, anthropic_messages = self._convert_messages(normalized_messages)
        kwargs = apply_thinking_level(kwargs, ANTHROPIC_COMPAT)
        request_kwargs = dict(kwargs)
        tools = self._resolve_tools_with_web_search(request_kwargs)
        request_kwargs.pop("tools", None)
        if tools:
            request_kwargs["tools"] = tools
        if self._supports_temperature(model):
            request_kwargs["temperature"] = temperature
        async with self.async_client.messages.stream(
            model=model,
            messages=anthropic_messages,
            system=system,
            max_tokens=max_tokens or 4096,
            **request_kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(content=text, finish_reason=None)

            # After the text stream, pull tool calls + usage from the final
            # message (Anthropic only exposes assembled tool_use blocks there).
            final = await stream.get_final_message()
            tool_calls = self._extract_tool_calls(final.content)
            usage = None
            if getattr(final, "usage", None):
                u = final.usage
                cached = getattr(u, "cache_read_input_tokens", None)
                usage = {
                    "input_tokens": int(getattr(u, "input_tokens", 0) or 0),
                    "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
                    "cached_tokens": int(cached or 0),
                    "total_tokens": int(getattr(u, "input_tokens", 0) or 0)
                    + int(getattr(u, "output_tokens", 0) or 0),
                }
            if tool_calls or usage:
                yield StreamChunk(content="", tool_calls=tool_calls, usage=usage)
