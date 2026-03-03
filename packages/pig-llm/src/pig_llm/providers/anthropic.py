"""Anthropic provider implementation."""

import json
from collections.abc import AsyncIterator, Iterator

import anthropic

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class AnthropicProvider(Provider):
    """Anthropic (Claude) provider implementation."""

    def __init__(self, config: Config):
        """Initialize Anthropic provider."""
        self.config = config
        self.client = anthropic.Anthropic(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )
        self.async_client = anthropic.AsyncAnthropic(
            api_key=config.api_key,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

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

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        system, anthropic_messages = self._convert_messages(messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))
        if tools:
            kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
            kwargs["tools"] = tools

        response = self.client.messages.create(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
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
        system, anthropic_messages = self._convert_messages(messages)

        with self.client.messages.stream(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
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
        system, anthropic_messages = self._convert_messages(messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))
        if tools:
            kwargs = {k: v for k, v in kwargs.items() if k != "tools"}
            kwargs["tools"] = tools

        response = await self.async_client.messages.create(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
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
        system, anthropic_messages = self._convert_messages(messages)

        async with self.async_client.messages.stream(
            model=model,
            messages=anthropic_messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield StreamChunk(content=text, finish_reason=None)
