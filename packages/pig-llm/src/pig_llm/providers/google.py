"""Google Gemini provider implementation (New SDK)."""

import base64
import json
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from google import genai
from google.genai import types

from ..compat import OPENAI_COMPAT, normalize_messages
from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class GoogleProvider(Provider):
    """Google Gemini provider implementation using new google-genai SDK."""

    @staticmethod
    def _tool_call_dict(part: Any, fc: Any) -> dict[str, Any]:
        """Build a canonical tool-call dict, preserving Gemini's thought_signature.

        Gemini 3 requires the opaque per-call ``thought_signature`` (bytes, on the
        Part) to be echoed back on the next turn or it rejects the request. Carry
        it base64-encoded in metadata so it survives JSON session storage.
        """
        call_id = f"call_{abs(hash(f'{fc.name}_{time.time()}'))}"
        sig = getattr(part, "thought_signature", None)
        meta = {}
        if sig:
            meta["thought_signature"] = base64.b64encode(sig).decode("ascii")
        return {
            "id": call_id,
            "type": "function",
            "function": {"name": fc.name, "arguments": json.dumps(dict(fc.args))},
            "metadata": meta,
        }

    _MODEL_THINKING_LEVEL_MAPS = {
        "gemini-3-pro-preview": {"minimal": None, "low": "LOW", "medium": None, "high": "HIGH"},
        "gemini-3.1-pro-preview": {
            "minimal": None,
            "low": "LOW",
            "medium": None,
            "high": "HIGH",
        },
        "gemini-3.1-pro-preview-customtools": {
            "minimal": None,
            "low": "LOW",
            "medium": None,
            "high": "HIGH",
        },
        "gemma-4-26b-a4b-it": {
            "minimal": "MINIMAL",
            "low": None,
            "medium": None,
            "high": "HIGH",
        },
        "gemma-4-31b-it": {
            "minimal": "MINIMAL",
            "low": None,
            "medium": None,
            "high": "HIGH",
        },
    }

    def __init__(self, config: Config):
        """Initialize Google provider."""
        self.config = config
        self.client: Any = genai.Client(api_key=config.api_key)

    def _convert_messages(self, messages: list[Message]) -> tuple[list[types.Content], str | None]:
        """Convert internal messages to Google Gemini format.

        Returns:
            List of Content objects for Gemini API
        """
        contents: list[types.Content] = []
        system_instruction: str | None = None

        for msg in messages:
            if msg.role == "system":
                # Store system message separately
                system_instruction = msg.content

            elif msg.role == "assistant" and msg.metadata and "tool_calls" in msg.metadata:
                # Rebuild assistant message with function_call
                parts: list[types.Part] = []

                # Add text part if present
                if msg.content:
                    parts.append(types.Part(text=msg.content))

                # Add function_call parts. Gemini 3 requires the original
                # thought_signature to be echoed back on the Part.
                for tc in msg.metadata["tool_calls"]:
                    function_call = types.FunctionCall(
                        name=tc["function"]["name"],
                        args=json.loads(tc["function"]["arguments"]),
                    )
                    sig_b64 = (tc.get("metadata") or {}).get("thought_signature")
                    thought_signature = base64.b64decode(sig_b64) if sig_b64 else None
                    parts.append(
                        types.Part(
                            function_call=function_call,
                            thought_signature=thought_signature,
                        )
                    )

                contents.append(types.Content(role="model", parts=parts))

            elif msg.role == "tool" and msg.metadata:
                # Convert tool result to function_response. The agent stores the
                # function name under "name"; accept "function_name" too. Gemini
                # rejects an empty name, so fall back to matching the call id
                # against the preceding assistant tool_calls when absent.
                function_name = msg.metadata.get("name") or msg.metadata.get("function_name")
                if not function_name:
                    tool_call_id = msg.metadata.get("tool_call_id")
                    for prev in reversed(contents):
                        for part in getattr(prev, "parts", []) or []:
                            fc = getattr(part, "function_call", None)
                            if fc and (
                                tool_call_id is None or getattr(fc, "id", None) == tool_call_id
                            ):
                                function_name = fc.name
                                break
                        if function_name:
                            break
                parts = [
                    types.Part.from_function_response(
                        name=function_name or "tool", response={"result": msg.content}
                    )
                ]
                contents.append(types.Content(role="user", parts=parts))

            else:
                # Regular message
                role = "model" if msg.role == "assistant" else "user"
                contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))

        return contents, system_instruction

    @staticmethod
    def _extract_tool_calls(response: Any) -> list[dict[str, Any]] | None:
        """Extract function_call from Gemini response."""
        if not response.candidates:
            return None

        tool_calls = []

        for candidate in response.candidates:
            for part in candidate.content.parts:
                # Check if this part has a function_call
                if hasattr(part, "function_call") and part.function_call:
                    tool_calls.append(GoogleProvider._tool_call_dict(part, part.function_call))

        return tool_calls if tool_calls else None

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[Any] | None:
        """Convert OpenAI-style tools to Gemini format."""
        if not tools:
            return None

        function_declarations: list[types.FunctionDeclaration] = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=func["name"],
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    )
                )

        if function_declarations:
            return [types.Tool(function_declarations=function_declarations)]

        return None

    def _thinking_config(self, model: str, level: str | None) -> types.ThinkingConfig | None:
        """Map pig thinking levels onto google-genai ThinkingConfig."""
        if level is None:
            return None
        if level == "off":
            return types.ThinkingConfig(thinking_budget=0)
        model_map = self._MODEL_THINKING_LEVEL_MAPS.get(model.lower())
        if model_map is not None:
            mapped = model_map.get(level)
            if mapped is None:
                return None
            return types.ThinkingConfig(thinking_level=types.ThinkingLevel(mapped))
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel(level.upper()))

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> Response:
        """Generate a completion."""
        # Convert messages
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=False,
        )
        contents, system_instruction = self._convert_messages(normalized_messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
            thinking_config=self._thinking_config(model, kwargs.get("thinking_level")),
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
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Stream a completion."""
        # Convert messages
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=False,
        )
        contents, system_instruction = self._convert_messages(normalized_messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
            thinking_config=self._thinking_config(model, kwargs.get("thinking_level")),
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
        **kwargs: Any,
    ) -> Response:
        """Async generate a completion."""
        # Convert messages
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=False,
        )
        contents, system_instruction = self._convert_messages(normalized_messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
            thinking_config=self._thinking_config(model, kwargs.get("thinking_level")),
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
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        # Convert messages
        normalized_messages = normalize_messages(
            messages,
            OPENAI_COMPAT,
            supports_developer_role=False,
        )
        contents, system_instruction = self._convert_messages(normalized_messages)

        # Convert tools if present
        tools = self._convert_tools(kwargs.get("tools"))

        # Build config
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            tools=tools,
            system_instruction=system_instruction,
            thinking_config=self._thinking_config(model, kwargs.get("thinking_level")),
        )

        # Generate content with streaming (async)
        response_stream = await self.client.aio.models.generate_content_stream(
            model=model, contents=contents, config=config
        )

        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, int] | None = None
        async for chunk in response_stream:
            if chunk.candidates and chunk.candidates[0].content.parts:
                for part in chunk.candidates[0].content.parts:
                    if getattr(part, "text", None):
                        yield StreamChunk(content=part.text, finish_reason=None)
                    fc = getattr(part, "function_call", None)
                    if fc:
                        tool_calls.append(self._tool_call_dict(part, fc))
            # Usage arrives on the final chunk's usage_metadata.
            meta = getattr(chunk, "usage_metadata", None)
            if meta:
                cached = getattr(meta, "cached_content_token_count", None)
                usage = {
                    "input_tokens": int(getattr(meta, "prompt_token_count", 0) or 0),
                    "output_tokens": int(getattr(meta, "candidates_token_count", 0) or 0),
                    "cached_tokens": int(cached or 0),
                    "total_tokens": int(getattr(meta, "total_token_count", 0) or 0),
                }

        # Emit assembled tool calls and/or usage on a trailing chunk, matching
        # the OpenAI-compatible streaming contract the agent loop consumes.
        if tool_calls or usage:
            yield StreamChunk(content="", tool_calls=tool_calls or None, usage=usage)
