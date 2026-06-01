"""Regression tests for Google provider compatibility behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pig_llm.config import Config
from pig_llm.models import Message
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
