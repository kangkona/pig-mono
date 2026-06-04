"""Regression tests for Google provider compatibility behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pig_llm.config import Config
from pig_llm.models import Message

pytest.importorskip("google.genai")

from pig_llm.providers.google import GoogleProvider


def _provider_with_client(sync_generate: Mock, async_generate: AsyncMock) -> GoogleProvider:
    sync_models = SimpleNamespace(
        generate_content=sync_generate,
        generate_content_stream=Mock(return_value=[]),
    )
    async_models = SimpleNamespace(
        generate_content=async_generate,
        generate_content_stream=AsyncMock(return_value=[]),
    )
    client = SimpleNamespace(
        models=sync_models,
        aio=SimpleNamespace(models=async_models),
    )

    with patch("pig_llm.providers.google.genai.Client", return_value=client):
        return GoogleProvider(Config(provider="google", api_key="test"))


def test_google_provider_maps_thinking_level_to_max_output_tokens() -> None:
    response = SimpleNamespace(
        candidates=[],
        usage_metadata=None,
        id="resp-1",
    )
    provider = _provider_with_client(Mock(return_value=response), AsyncMock(return_value=response))

    provider.complete(
        [Message(role="user", content="hello")],
        model="gemini-2.5-flash",
        thinking_level="high",
        max_tokens=256,
    )

    config = provider.client.models.generate_content.call_args.kwargs["config"]
    assert config.max_output_tokens == 256


def test_google_provider_thinking_off_does_not_break_generation() -> None:
    response = SimpleNamespace(
        candidates=[],
        usage_metadata=None,
        id="resp-1",
    )
    provider = _provider_with_client(Mock(return_value=response), AsyncMock(return_value=response))

    provider.complete(
        [Message(role="user", content="hello")],
        model="gemini-2.5-flash",
        thinking_level="off",
    )

    provider.client.models.generate_content.assert_called_once()

    config = provider.client.models.generate_content.call_args.kwargs["config"]
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_budget == 0


def test_google_provider_maps_thinking_level_into_thinking_config() -> None:
    response = SimpleNamespace(
        candidates=[],
        usage_metadata=None,
        id="resp-1",
    )
    provider = _provider_with_client(Mock(return_value=response), AsyncMock(return_value=response))

    provider.complete(
        [Message(role="user", content="hello")],
        model="gemini-2.5-flash",
        thinking_level="high",
    )

    config = provider.client.models.generate_content.call_args.kwargs["config"]
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level is not None


def test_google_provider_uses_google_thinking_level_enum() -> None:
    from google.genai import types

    response = SimpleNamespace(
        candidates=[],
        usage_metadata=None,
        id="resp-1",
    )
    provider = _provider_with_client(Mock(return_value=response), AsyncMock(return_value=response))

    provider.complete(
        [Message(role="user", content="hello")],
        model="gemini-2.5-flash",
        thinking_level="high",
    )

    config = provider.client.models.generate_content.call_args.kwargs["config"]
    assert config.thinking_config.thinking_level == types.ThinkingLevel.HIGH


def test_google_provider_normalizes_explicit_developer_role_to_system_instruction() -> None:
    response = SimpleNamespace(
        candidates=[],
        usage_metadata=None,
        id="resp-1",
    )
    provider = _provider_with_client(Mock(return_value=response), AsyncMock(return_value=response))

    provider.complete(
        [
            Message(role="developer", content="rules"),
            Message(role="user", content="hello"),
        ],
        model="gemini-2.5-flash",
    )

    call_kwargs = provider.client.models.generate_content.call_args.kwargs
    config = call_kwargs["config"]
    assert config.system_instruction == "rules"
    assert len(call_kwargs["contents"]) == 1
    assert call_kwargs["contents"][0].role == "user"


@pytest.mark.asyncio
async def test_google_astream_emits_tool_calls_and_usage() -> None:
    """Native Google streaming surfaces function_call tool calls + usage (Phase B)."""

    class _Stream:
        def __aiter__(self):
            async def gen():
                # text delta
                yield SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=SimpleNamespace(
                                parts=[SimpleNamespace(text="checking ", function_call=None)]
                            )
                        )
                    ],
                    usage_metadata=None,
                )
                # function_call part + usage on the final chunk
                yield SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=SimpleNamespace(
                                parts=[
                                    SimpleNamespace(
                                        text=None,
                                        function_call=SimpleNamespace(
                                            name="get_weather", args={"city": "Tokyo"}
                                        ),
                                    )
                                ]
                            )
                        )
                    ],
                    usage_metadata=SimpleNamespace(
                        prompt_token_count=120,
                        candidates_token_count=18,
                        total_token_count=138,
                        cached_content_token_count=40,
                    ),
                )

            return gen()

    provider = _provider_with_client(Mock(), AsyncMock())
    provider.client.aio.models.generate_content_stream = AsyncMock(return_value=_Stream())

    chunks = []
    async for chunk in provider.astream(
        [Message(role="user", content="weather?")],
        model="gemini-3.5-flash",
        tools=[{"type": "function", "function": {"name": "get_weather", "parameters": {}}}],
    ):
        chunks.append(chunk)

    text = "".join(c.content for c in chunks if c.content)
    assert text == "checking "
    tool_chunks = [c for c in chunks if c.tool_calls]
    assert tool_chunks and tool_chunks[-1].tool_calls[0]["function"]["name"] == "get_weather"
    usages = [c.usage for c in chunks if c.usage]
    assert usages[-1] == {
        "input_tokens": 120,
        "output_tokens": 18,
        "cached_tokens": 40,
        "total_tokens": 138,
    }


def test_google_tool_result_carries_function_name() -> None:
    """A tool result must convert to a function_response with a non-empty name.

    Regression: the converter read metadata['function_name'] but the agent
    stores it under 'name', so Gemini rejected the follow-up turn with
    "Name cannot be empty" (400 INVALID_ARGUMENT).
    """
    provider = _provider_with_client(Mock(), AsyncMock())
    messages = [
        Message(role="user", content="weather?"),
        Message(
            role="assistant",
            content="",
            metadata={
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": "{}"},
                    }
                ]
            },
        ),
        Message(
            role="tool", content="sunny", metadata={"tool_call_id": "c1", "name": "get_weather"}
        ),
    ]
    contents, _ = provider._convert_messages(messages)
    names = [
        part.function_response.name
        for c in contents
        for part in c.parts
        if getattr(part, "function_response", None)
    ]
    assert names == ["get_weather"]


def test_google_preserves_thought_signature_round_trip() -> None:
    """Gemini 3 requires echoing the function_call thought_signature back.

    Regression: the signature (bytes on the Part) was dropped, so the next turn
    failed with 400 "Function call is missing a thought_signature". It must be
    carried (base64) through the tool_call dict and restored onto the rebuilt
    Part.
    """
    import base64

    provider = _provider_with_client(Mock(), AsyncMock())
    sig = b"\x01\x02\xfftok"
    part = SimpleNamespace(
        function_call=SimpleNamespace(name="list_files", args={}), thought_signature=sig
    )
    tc = provider._tool_call_dict(part, part.function_call)
    assert base64.b64decode(tc["metadata"]["thought_signature"]) == sig

    rebuilt, _ = provider._convert_messages(
        [Message(role="assistant", content="", metadata={"tool_calls": [tc]})]
    )
    fc_part = rebuilt[0].parts[0]
    assert fc_part.thought_signature == sig
    assert fc_part.function_call.name == "list_files"
