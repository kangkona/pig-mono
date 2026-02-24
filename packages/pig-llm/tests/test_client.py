"""Tests for LLM client."""

import pytest
from unittest.mock import Mock, patch
from pig_llm import LLM, Config, Message


def test_llm_initialization_with_provider():
    """Test LLM initialization with provider."""
    with patch('pig_llm.providers.openai.OpenAIProvider') as MockProvider:
        MockProvider.return_value = Mock()
        llm = LLM(provider="openai", api_key="test-key")
        assert llm.config.provider == "openai"
        assert llm.config.api_key == "test-key"


def test_llm_initialization_with_config():
    """Test LLM initialization with config."""
    config = Config(provider="openai", api_key="test-key", model="gpt-4")
    with patch('pig_llm.providers.openai.OpenAIProvider') as MockProvider:
        MockProvider.return_value = Mock()
        llm = LLM(config=config)
        assert llm.config == config


def test_llm_unknown_provider():
    """Test unknown provider raises error."""
    with pytest.raises((ValueError, Exception)):
        LLM(provider="unknown", api_key="test")


def test_llm_complete_creates_messages():
    """Test complete method creates proper messages."""
    with patch('pig_llm.providers.openai.OpenAIProvider') as MockProvider:
        mock_provider = Mock()
        MockProvider.return_value = mock_provider

        llm = LLM(provider="openai", api_key="test")
        llm.complete("Hello", system="You are helpful")

        assert mock_provider.complete.called
        call_args = mock_provider.complete.call_args
        messages = call_args.kwargs['messages']

        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"


def test_llm_complete_without_system():
    """Test complete without system message."""
    with patch('pig_llm.providers.openai.OpenAIProvider') as MockProvider:
        mock_provider = Mock()
        MockProvider.return_value = mock_provider

        llm = LLM(provider="openai", api_key="test")
        llm.complete("Hello")

        call_args = mock_provider.complete.call_args
        messages = call_args.kwargs['messages']

        assert len(messages) == 1
        assert messages[0].role == "user"


def test_llm_chat():
    """Test chat method with message list."""
    with patch('pig_llm.providers.openai.OpenAIProvider') as MockProvider:
        mock_provider = Mock()
        MockProvider.return_value = mock_provider

        llm = LLM(provider="openai", api_key="test")
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi"),
            Message(role="user", content="How are you?"),
        ]
        llm.chat(messages)

        call_args = mock_provider.complete.call_args
        passed_messages = call_args.kwargs['messages']
        assert len(passed_messages) == 3
