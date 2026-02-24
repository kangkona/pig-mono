"""Tests for pig-ai package (integration)."""

import pytest
from unittest.mock import patch


def test_package_imports():
    """Test package imports."""
    from pig_llm import LLM, Config, Message, Response
    assert LLM is not None
    assert Config is not None
    assert Message is not None
    assert Response is not None


@patch('pig_llm.client.OpenAIProvider')
def test_basic_integration(mock_provider):
    """Test basic LLM integration."""
    from pig_llm import LLM, Config, Message
    
    config = Config(provider="openai", model="gpt-4", api_key="test")
    assert config.provider == "openai"
    
    llm = LLM(config=config)
    assert llm.config == config


@pytest.mark.skip(reason="Requires API key")
def test_llm_complete_real():
    """Test LLM completion with real API (integration test)."""
    import os
    from pig_llm import LLM
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")
    
    llm = LLM(provider="openai", api_key=api_key)
    response = llm.complete("Say hello")
    assert response.content
    assert response.model
