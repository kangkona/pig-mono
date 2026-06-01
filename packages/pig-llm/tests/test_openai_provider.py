"""Tests for the OpenAI provider."""

from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pig_llm.config import Config
from pig_llm.models import Message
from pig_llm.providers.openai import OpenAIProvider


def _completion_response() -> SimpleNamespace:
    return SimpleNamespace(
        id="chatcmpl-test",
        model="gpt-5.2",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        ),
    )


def _stream_chunk() -> SimpleNamespace:
    return SimpleNamespace(
        id="chunk-test",
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content="ok"),
                finish_reason=None,
            )
        ],
    )


class _AsyncChunks:
    def __init__(self, chunks: list[SimpleNamespace]):
        self._chunks = iter(chunks)

    def __aiter__(self) -> "_AsyncChunks":
        return self

    async def __anext__(self) -> SimpleNamespace:
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _provider_with_clients(sync_create: Mock, async_create: AsyncMock) -> OpenAIProvider:
    sync_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=sync_create),
        )
    )
    async_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=async_create),
        )
    )

    with (
        patch("pig_llm.providers.openai.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.openai.openai.AsyncOpenAI", return_value=async_client),
    ):
        return OpenAIProvider(Config(api_key="test-key"))


def _messages() -> list[Message]:
    return [Message(role="user", content="Hello")]


def _assert_uses_max_completion_tokens(call_kwargs: Mapping[str, Any]) -> None:
    assert call_kwargs["max_completion_tokens"] == 128
    assert "max_tokens" not in call_kwargs


def test_complete_sends_max_completion_tokens_to_openai() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(_messages(), model="gpt-5.2", max_tokens=128)

    _assert_uses_max_completion_tokens(sync_create.call_args.kwargs)


def test_stream_sends_max_completion_tokens_to_openai() -> None:
    sync_create = Mock(return_value=iter([_stream_chunk()]))
    provider = _provider_with_clients(sync_create, AsyncMock())

    list(provider.stream(_messages(), model="gpt-5.2", max_tokens=128))

    _assert_uses_max_completion_tokens(sync_create.call_args.kwargs)


def test_complete_merges_session_id_and_custom_headers() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.2",
        session_id="session-123",
        headers={"X-Test": "1"},
    )

    assert sync_create.call_args.kwargs["extra_headers"] == {
        "session-id": "session-123",
        "X-Test": "1",
    }
    assert "headers" not in sync_create.call_args.kwargs
    assert "session_id" not in sync_create.call_args.kwargs


def test_complete_falls_back_to_choice_usage_when_response_usage_missing() -> None:
    response = SimpleNamespace(
        id="chatcmpl-test",
        model="gpt-5.2",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok"),
                finish_reason="stop",
                usage=SimpleNamespace(
                    prompt_tokens=7,
                    completion_tokens=3,
                    total_tokens=10,
                ),
            )
        ],
        usage=None,
    )
    sync_create = Mock(return_value=response)
    provider = _provider_with_clients(sync_create, AsyncMock())

    result = provider.complete(_messages(), model="gpt-5.2")

    assert result.usage == {
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "total_tokens": 10,
    }


@pytest.mark.asyncio
async def test_acomplete_sends_max_completion_tokens_to_openai() -> None:
    async_create = AsyncMock(return_value=_completion_response())
    provider = _provider_with_clients(Mock(), async_create)

    await provider.acomplete(_messages(), model="gpt-5.2", max_tokens=128)

    _assert_uses_max_completion_tokens(async_create.call_args.kwargs)


@pytest.mark.asyncio
async def test_astream_sends_max_completion_tokens_to_openai() -> None:
    async_create = AsyncMock(return_value=_AsyncChunks([_stream_chunk()]))
    provider = _provider_with_clients(Mock(), async_create)

    chunks = [
        chunk async for chunk in provider.astream(_messages(), model="gpt-5.2", max_tokens=128)
    ]

    assert len(chunks) == 1
    _assert_uses_max_completion_tokens(async_create.call_args.kwargs)
