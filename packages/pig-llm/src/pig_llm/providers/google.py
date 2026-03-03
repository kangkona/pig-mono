"""Google Gemini provider implementation (New SDK)."""

import json
import time
from collections.abc import AsyncIterator, Iterator

from google import genai
from google.genai import types

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class GoogleProvider(Provider):
    """Google Gemini provider implementation using new google-genai SDK."""

    def __init__(self, config: Config):
        """Initialize Google provider."""
        self.config = config
        self.client = genai.Client(api_key=config.api_key)

    def _convert_messages(self, messages: list[Message]) -> list:
        """Convert internal messages to Google Gemini format.

        Returns:
            List of Content objects for Gemini API
        """
        contents = []
        system_instruction = None

        for msg in messages:
            if msg.role == "system":
                # Store system message separately
                system_instruction = msg.content

            elif msg.role == "assistant" and msg.metadata and "tool_calls" in msg.metadata:
                # Rebuild assistant message with function_call
                parts = []

                # Add text part if present
                if msg.content:
                    parts.append(types.Part(text=msg.content))

                # Add function_call parts
                for tc in msg.metadata["tool_calls"]:
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                name=tc["function"]["name"],
                                args=json.loads(tc["function"]["arguments"]),
                            )
                        )
                    )

                contents.append(types.Content(role="model", parts=parts))

            elif msg.role == "tool" and msg.metadata:
                # Convert tool result to function_response
                function_name = msg.metadata.get("function_name")
                parts = [
                    types.Part.from_function_response(
                        name=function_name, response={"result": msg.content}
                    )
                ]
                contents.append(types.Content(role="user", parts=parts))

            else:
                # Regular message
                role = "model" if msg.role == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))

        return contents, system_instruction

    @staticmethod
    def _extract_tool_calls(response) -> list[dict] | None:
        """Extract function_call from Gemini response."""
        if not response.candidates:
            return None

        tool_calls = []

        for candidate in response.candidates:
            for part in candidate.content.parts:
                # Check if this part has a function_call
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call

                    # Generate unique ID (Gemini doesn't provide one)
                    call_id = f"call_{abs(hash(f'{fc.name}_{time.time()}'))}"

                    tool_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": fc.name,
                                "arguments": json.dumps(dict(fc.args)),
                            },
                        }
                    )

        return tool_calls if tool_calls else None

    def _convert_tools(self, tools: list[dict] | None) -> list | None:
        """Convert OpenAI-style tools to Gemini format."""
        if not tools:
            return None

        function_declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                function_declarations.append(
                    {
                        "name": func["name"],
                        "description": func.get("description", ""),
                        "parameters": func.get("parameters", {}),
                    }
                )

        if function_declarations:
            return [types.Tool(function_declarations=function_declarations)]

        return None

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        # Convert messages
        contents, system_instruction = self._convert_messages(messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
        )

        # Generate content
        response = self.client.models.generate_content(
            model=model, contents=contents, config=config
        )

        # Extract text content
        content = ""
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    content += part.text

        # Extract tool_calls
        tool_calls = self._extract_tool_calls(response)

        # Build usage
        usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
            }

        # Get finish_reason
        finish_reason = None
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = str(response.candidates[0].finish_reason)

        return Response(
            content=content,
            model=model,
            usage=usage,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            metadata={"response_id": getattr(response, "id", None)},
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
        # Convert messages
        contents, system_instruction = self._convert_messages(messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
        )

        # Generate content with streaming
        response_stream = self.client.models.generate_content_stream(
            model=model, contents=contents, config=config
        )

        for chunk in response_stream:
            if chunk.candidates and chunk.candidates[0].content.parts:
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        yield StreamChunk(
                            content=part.text,
                            finish_reason=None,
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
        # Convert messages
        contents, system_instruction = self._convert_messages(messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
        )

        # Generate content (async)
        response = await self.client.aio.models.generate_content(
            model=model, contents=contents, config=config
        )

        # Extract text content
        content = ""
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    content += part.text

        # Extract tool_calls
        tool_calls = self._extract_tool_calls(response)

        # Build usage
        usage = None
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": response.usage_metadata.total_token_count,
            }

        # Get finish_reason
        finish_reason = None
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = str(response.candidates[0].finish_reason)

        return Response(
            content=content,
            model=model,
            usage=usage,
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            metadata={"response_id": getattr(response, "id", None)},
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
        # Convert messages
        contents, system_instruction = self._convert_messages(messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
        )

        # Generate content with streaming (async)
        response_stream = await self.client.aio.models.generate_content_stream(
            model=model, contents=contents, config=config
        )

        async for chunk in response_stream:
            if chunk.candidates and chunk.candidates[0].content.parts:
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, "text") and part.text:
                        yield StreamChunk(
                            content=part.text,
                            finish_reason=None,
                        )
