"""Tests for resilience support."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import patch

from pig_agent_core.resilience.retry import resilient_call
from pig_coding_agent.resilience import (
    create_profile_manager_from_env,
    get_profile_status,
)
from pig_llm import Response


def test_create_profile_manager_no_keys():
    """Test creating profile manager with no API keys."""
    with patch.dict(os.environ, {}, clear=True):
        manager = create_profile_manager_from_env()
        assert manager is None


def test_create_profile_manager_single_key():
    """Test creating profile manager with single API key."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}, clear=True):
        manager = create_profile_manager_from_env()
        assert manager is not None
        assert len(manager.profiles) == 1
        assert manager.profiles[0].api_key == "sk-test123"
        assert manager.profiles[0].model == "gpt-4"
        assert manager.profiles[0].metadata["provider"] == "openai"


def test_create_profile_manager_multiple_keys():
    """Test creating profile manager with multiple API keys."""
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "sk-test1",
            "OPENAI_API_KEY_2": "sk-test2",
            "ANTHROPIC_API_KEY": "sk-ant-test1",
        },
        clear=True,
    ):
        manager = create_profile_manager_from_env()
        assert manager is not None
        assert len(manager.profiles) == 3

        # Check OpenAI keys
        openai_profiles = [p for p in manager.profiles if p.metadata["provider"] == "openai"]
        assert len(openai_profiles) == 2
        assert openai_profiles[0].api_key == "sk-test1"
        assert openai_profiles[1].api_key == "sk-test2"

        # Check Anthropic key
        anthropic_profiles = [p for p in manager.profiles if p.metadata["provider"] == "anthropic"]
        assert len(anthropic_profiles) == 1
        assert anthropic_profiles[0].api_key == "sk-ant-test1"


def test_mixed_provider_failover_never_builds_openai_client_with_anthropic_key():
    constructed: list[tuple[str, str]] = []

    class OfflineOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key
            self.config = SimpleNamespace(
                provider="openai",
                api_key=api_key,
                model="gpt-4",
            )

        @classmethod
        def with_profile(cls, llm, *, api_key: str, model: str):
            del llm
            constructed.append((api_key, model))
            return cls(api_key)

        async def achat(self, *, messages, **kwargs):
            del messages, kwargs
            if self.api_key == "openai-bad":
                raise Exception("invalid api key")
            return Response(content="ok", model="gpt-4")

    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "openai-bad",
            "OPENAI_API_KEY_2": "openai-good",
            "ANTHROPIC_API_KEY": "anthropic-secret",
        },
        clear=True,
    ):
        manager = create_profile_manager_from_env()
        assert manager is not None
        result = asyncio.run(
            resilient_call(
                OfflineOpenAI("openai-bad"),
                [],
                profile_manager=manager,
                max_retries=1,
            )
        )

    assert result == "ok"
    assert constructed == [("openai-good", "gpt-4")]
    assert manager.active_profile is not None
    assert manager.active_profile.provider == "openai"
    assert manager.get_fallback_model("gpt-4", "openai") == "gpt-3.5-turbo"
    assert manager.get_fallback_model("gpt-4", "anthropic") == "claude-3-5-sonnet-20241022"


def test_create_profile_manager_fallback_models():
    """Test profile manager has fallback models configured."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
        manager = create_profile_manager_from_env()
        assert manager is not None
        assert len(manager.fallback_models) > 0
        assert "gpt-4" in manager.fallback_models
        assert "gpt-3.5-turbo" in manager.fallback_models


def test_get_profile_status():
    """Test getting profile status."""
    with patch.dict(
        os.environ,
        {"OPENAI_API_KEY": "sk-test1", "OPENAI_API_KEY_2": "sk-test2"},
        clear=True,
    ):
        manager = create_profile_manager_from_env()
        assert manager is not None

        status = get_profile_status(manager)

        assert status["total_profiles"] == 2
        assert status["available_profiles"] == 2
        assert status["cooldown_profiles"] == 0
        assert len(status["profiles"]) == 2

        # Check profile info structure
        profile_info = status["profiles"][0]
        assert "model" in profile_info
        assert "provider" in profile_info
        assert "key_index" in profile_info
        assert "available" in profile_info
        assert profile_info["available"] is True


def test_get_profile_status_with_cooldown():
    """Test profile status with cooldown."""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
        manager = create_profile_manager_from_env()
        assert manager is not None

        # Put profile in cooldown
        profile = manager.profiles[0]
        profile.set_cooldown(60.0)

        status = get_profile_status(manager)

        assert status["total_profiles"] == 1
        assert status["available_profiles"] == 0
        assert status["cooldown_profiles"] == 1
        assert status["profiles"][0]["available"] is False
        assert status["profiles"][0]["cooldown_until"] is not None
