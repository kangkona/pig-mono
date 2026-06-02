"""Regression tests for provider compatibility absorbed from pi-mono."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pig_llm.compat import (
    ANTHROPIC_COMPAT,
    OPENAI_COMPAT,
    OPENROUTER_COMPAT,
    apply_thinking_level,
    build_token_limit_param,
    classify_provider_error,
    is_context_overflow,
)
from pig_llm.config import Config
from pig_llm.models import Message
from pig_llm.providers.openrouter import OpenRouterProvider


class _AsyncTextStream:
    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _anthropic_completion_response() -> SimpleNamespace:
    text_block = SimpleNamespace(type="text", text="ok")
    return SimpleNamespace(
        id="msg_123",
        model="claude-opus-4-7",
        content=[text_block],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def _completion_response() -> SimpleNamespace:
    return SimpleNamespace(
        id="chatcmpl-test",
        model="moonshotai/kimi-k2.6",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def test_openrouter_kimi_keeps_system_role_instead_of_developer() -> None:
    create = Mock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    provider.complete(
        [
            Message(role="system", content="rules", metadata={"role": "developer"}),
            Message(role="user", content="hi"),
        ],
        model="moonshotai/kimi-k2.6",
    )

    messages = create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "rules"}
    assert all(message["role"] != "developer" for message in messages)
    assert "max_tokens" not in create.call_args.kwargs


def test_openrouter_normalizes_explicit_developer_role_messages_to_system() -> None:
    create = Mock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    provider.complete(
        [
            Message(role="developer", content="rules"),
            Message(role="user", content="hi"),
        ],
        model="moonshotai/kimi-k2.6",
    )

    messages = create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "rules"}
    assert all(message["role"] != "developer" for message in messages)


def test_openai_compatible_omits_model_derived_default_output_caps() -> None:
    params = build_token_limit_param(
        128000,
        param_name="max_tokens",
        compat=OPENAI_COMPAT,
        explicit=False,
    )

    assert params == {}


def test_openai_completion_token_param_skips_legacy_max_tokens() -> None:
    params = build_token_limit_param(
        512,
        param_name="max_completion_tokens",
        compat=OPENAI_COMPAT,
    )

    assert params == {"max_completion_tokens": 512}


def test_quota_429_is_not_classified_as_retryable() -> None:
    classification = classify_provider_error(
        "HTTP 429: insufficient quota; please check your billing details",
        OPENROUTER_COMPAT,
    )

    assert classification == "quota_or_billing"


def test_context_overflow_patterns_cover_multiple_providers() -> None:
    errors = [
        "maximum allowed input length is 128000 tokens",
        "request_too_large: prompt exceeds model context window",
        "This model's maximum context length is 8192 tokens",
    ]

    assert all(is_context_overflow(error, OPENROUTER_COMPAT) for error in errors)


def test_thinking_off_strips_unsupported_thinking_payloads() -> None:
    kwargs = apply_thinking_level(
        {
            "thinking_level": "off",
            "thinking": {"type": "enabled", "budget_tokens": 4096},
            "reasoning_effort": "high",
        },
        ANTHROPIC_COMPAT,
    )

    assert "thinking" not in kwargs
    assert "reasoning_effort" not in kwargs


def test_async_openrouter_uses_same_system_role_policy() -> None:
    create = AsyncMock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    import asyncio

    asyncio.run(
        provider.acomplete(
            [
                Message(role="system", content="rules", metadata={"role": "developer"}),
                Message(role="user", content="hi"),
            ],
            model="moonshotai/kimi-k2.6",
        )
    )

    messages = create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "max_tokens" not in create.call_args.kwargs


def test_openrouter_sets_session_id_header_for_affinity() -> None:
    create = Mock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    provider.complete(
        [Message(role="user", content="hello")],
        model="moonshotai/kimi-k2.6",
        session_id="session-abc",
    )

    assert create.call_args.kwargs["extra_headers"] == {
        "session_id": "session-abc",
        "x-client-request-id": "session-abc",
        "x-session-affinity": "session-abc",
        "session-id": "session-abc",
    }


def test_openrouter_uses_prompt_cache_for_long_retention() -> None:
    create = Mock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    provider.complete(
        [Message(role="user", content="hello")],
        model="moonshotai/kimi-k2.6",
        session_id="session-abc",
        cache_retention="long",
    )

    assert create.call_args.kwargs["prompt_cache_key"] == "session-abc"
    assert create.call_args.kwargs["prompt_cache_retention"] == "24h"


def test_openrouter_omits_prompt_cache_for_default_short_retention() -> None:
    create = Mock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    provider.complete(
        [Message(role="user", content="hello")],
        model="moonshotai/kimi-k2.6",
        session_id="session-abc",
    )

    assert "prompt_cache_key" not in create.call_args.kwargs
    assert "prompt_cache_retention" not in create.call_args.kwargs


def test_openrouter_reasoning_models_send_explicit_reasoning_off_payload() -> None:
    create = Mock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    provider.complete(
        [Message(role="user", content="hello")],
        model="deepseek/deepseek-r1",
        thinking_level="off",
    )

    assert create.call_args.kwargs["reasoning"] == {"effort": "none"}


def test_openrouter_reasoning_models_use_nested_reasoning_payload_when_enabled() -> None:
    create = Mock(return_value=_completion_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    provider.complete(
        [Message(role="user", content="hello")],
        model="deepseek/deepseek-r1",
        thinking_level="high",
    )

    assert create.call_args.kwargs["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_openrouter_falls_back_to_choice_usage_when_top_level_usage_missing() -> None:
    response = SimpleNamespace(
        id="chatcmpl-test",
        model="moonshotai/kimi-k2.6",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
                usage=SimpleNamespace(prompt_tokens=20, completion_tokens=5, total_tokens=25),
            )
        ],
        usage=None,
    )
    create = Mock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    with (
        patch("pig_llm.providers.openrouter.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openrouter.openai.AsyncOpenAI", return_value=client),
    ):
        provider = OpenRouterProvider(Config(provider="openrouter", api_key="test"))

    result = provider.complete(
        [Message(role="user", content="hello")],
        model="moonshotai/kimi-k2.6",
    )

    assert result.usage == {
        "prompt_tokens": 20,
        "completion_tokens": 5,
        "total_tokens": 25,
    }


def test_anthropic_opus_47_omits_temperature_param() -> None:
    create = Mock(return_value=_anthropic_completion_response())
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    async_client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock()))

    with (
        patch("pig_llm.providers.anthropic.anthropic.Anthropic", return_value=client),
        patch("pig_llm.providers.anthropic.anthropic.AsyncAnthropic", return_value=async_client),
    ):
        from pig_llm.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(Config(provider="anthropic", api_key="test"))

    provider.complete(
        [Message(role="user", content="hello")],
        model="claude-opus-4-7",
        temperature=0,
    )

    assert "temperature" not in create.call_args.kwargs


def test_anthropic_non_opus_47_models_keep_temperature_param() -> None:
    create = Mock(return_value=_anthropic_completion_response())
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    async_client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock()))

    with (
        patch("pig_llm.providers.anthropic.anthropic.Anthropic", return_value=client),
        patch("pig_llm.providers.anthropic.anthropic.AsyncAnthropic", return_value=async_client),
    ):
        from pig_llm.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(Config(provider="anthropic", api_key="test"))

    provider.complete(
        [Message(role="user", content="hello")],
        model="claude-sonnet-4-6",
        temperature=0,
    )

    assert create.call_args.kwargs["temperature"] == 0


def test_anthropic_opus_47_stream_omits_temperature_param() -> None:
    stream_ctx = Mock()
    stream_ctx.__enter__ = Mock(return_value=SimpleNamespace(text_stream=[]))
    stream_ctx.__exit__ = Mock(return_value=False)
    client = SimpleNamespace(messages=SimpleNamespace(stream=Mock(return_value=stream_ctx)))
    async_client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock()))

    with (
        patch("pig_llm.providers.anthropic.anthropic.Anthropic", return_value=client),
        patch("pig_llm.providers.anthropic.anthropic.AsyncAnthropic", return_value=async_client),
    ):
        from pig_llm.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(Config(provider="anthropic", api_key="test"))

    list(
        provider.stream(
            [Message(role="user", content="hello")],
            model="claude-opus-4-7",
            temperature=0,
        )
    )

    assert "temperature" not in client.messages.stream.call_args.kwargs


@patch("pig_llm.providers.anthropic.anthropic.AsyncAnthropic")
@patch("pig_llm.providers.anthropic.anthropic.Anthropic")
@pytest.mark.asyncio
async def test_anthropic_opus_47_astream_omits_temperature_param(
    mock_anthropic, mock_async_anthropic
) -> None:
    stream_ctx = AsyncMock()
    stream_ctx.__aenter__.return_value = SimpleNamespace(text_stream=_AsyncTextStream([]))
    stream_ctx.__aexit__.return_value = False
    mock_async_anthropic.return_value = SimpleNamespace(
        messages=SimpleNamespace(stream=Mock(return_value=stream_ctx))
    )
    mock_anthropic.return_value = SimpleNamespace(messages=SimpleNamespace(create=Mock()))

    from pig_llm.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider(Config(provider="anthropic", api_key="test"))

    chunks = [
        chunk
        async for chunk in provider.astream(
            [Message(role="user", content="hello")],
            model="claude-opus-4-7",
            temperature=0,
        )
    ]

    assert chunks == []
    assert "temperature" not in mock_async_anthropic.return_value.messages.stream.call_args.kwargs
