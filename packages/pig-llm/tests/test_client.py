"""Tests for LLM client."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pig_llm import LLM, Config, Message


def test_llm_initialization_with_provider():
    """Test LLM initialization with provider."""
    with patch("pig_llm.providers.openai.OpenAIProvider") as MockProvider:
        MockProvider.return_value = Mock()
        llm = LLM(provider="openai", api_key="test-key")
        assert llm.config.provider == "openai"
        assert llm.config.api_key == "test-key"


def test_llm_initialization_with_config():
    """Test LLM initialization with config."""
    config = Config(provider="openai", api_key="test-key", model="gpt-4")
    with patch("pig_llm.providers.openai.OpenAIProvider") as MockProvider:
        MockProvider.return_value = Mock()
        llm = LLM(config=config)
        assert llm.config == config


def test_llm_unknown_provider():
    """Test unknown provider raises error."""
    with pytest.raises((ValueError, Exception)):
        LLM(provider="unknown", api_key="test")


def test_llm_requires_explicit_api_key_for_known_provider():
    """Known providers should not silently rely on ambient SDK env fallbacks."""
    with pytest.raises(ValueError, match="No API key for provider: openai"):
        LLM(provider="openai")


def test_llm_allows_bedrock_without_api_key():
    mock_provider = Mock()
    mock_bedrock_class = Mock(return_value=mock_provider)
    fake_bedrock_module = SimpleNamespace(BedrockProvider=mock_bedrock_class)

    with patch("importlib.import_module", return_value=fake_bedrock_module) as mock_import:
        llm = LLM(provider="bedrock")

    assert llm.config.provider == "bedrock"
    assert llm.config.api_key is None
    mock_import.assert_called_once_with(".providers.bedrock", package="pig_llm")
    mock_bedrock_class.assert_called_once()


def test_llm_complete_creates_messages():
    """Test complete method creates proper messages."""
    with patch("pig_llm.providers.openai.OpenAIProvider") as MockProvider:
        mock_provider = Mock()
        MockProvider.return_value = mock_provider

        llm = LLM(provider="openai", api_key="test", model="gpt-4o-mini")
        llm.complete("Hello", system="You are helpful")

        assert mock_provider.complete.called
        call_args = mock_provider.complete.call_args
        messages = call_args.kwargs["messages"]

        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"


def test_llm_complete_without_system():
    """Test complete without system message."""
    with patch("pig_llm.providers.openai.OpenAIProvider") as MockProvider:
        mock_provider = Mock()
        MockProvider.return_value = mock_provider

        llm = LLM(provider="openai", api_key="test", model="gpt-4o-mini")
        llm.complete("Hello")

        call_args = mock_provider.complete.call_args
        messages = call_args.kwargs["messages"]

        assert len(messages) == 1
        assert messages[0].role == "user"


def test_llm_chat():
    """Test chat method with message list."""
    with patch("pig_llm.providers.openai.OpenAIProvider") as MockProvider:
        mock_provider = Mock()
        MockProvider.return_value = mock_provider

        llm = LLM(provider="openai", api_key="test", model="gpt-4o-mini")
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="How are you?"),
        ]
        llm.chat(messages)

        call_args = mock_provider.complete.call_args
        passed_messages = call_args.kwargs["messages"]
        assert len(passed_messages) == 3
