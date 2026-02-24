"""Tests for configuration."""

import pytest
from pig_llm.config import Config


def test_config_defaults():
    """Test default config values."""
    config = Config()
    assert config.provider == "openai"
    assert config.model == "gpt-4"
    assert config.temperature == 0.7
    assert config.timeout == 30
    assert config.max_retries == 3


def test_config_custom_values():
    """Test custom config values."""
    config = Config(
        provider="anthropic",
        model="claude-3",
        temperature=0.5,
        max_tokens=1000,
    )
    assert config.provider == "anthropic"
    assert config.model == "claude-3"
    assert config.temperature == 0.5
    assert config.max_tokens == 1000


def test_config_temperature_validation():
    """Test temperature validation."""
    with pytest.raises(ValueError):
        Config(temperature=-0.1)
    
    with pytest.raises(ValueError):
        Config(temperature=2.1)


def test_config_max_tokens_validation():
    """Test max tokens validation."""
    with pytest.raises(ValueError):
        Config(max_tokens=0)


def test_config_frozen():
    """Test config is frozen (immutable)."""
    config = Config()
    with pytest.raises(Exception):  # Pydantic ValidationError
        config.temperature = 0.5
