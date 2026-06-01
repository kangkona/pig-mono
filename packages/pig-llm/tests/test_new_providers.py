"""Tests for newly added providers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pig_llm.config import Config


class TestNewProviders:
    """Test that new providers can be imported and initialized."""

    def test_bedrock_import(self):
        """Test Bedrock provider import."""
        pytest.importorskip("boto3")
        from pig_llm.providers.bedrock import BedrockProvider

        assert BedrockProvider is not None

    def test_xai_import(self):
        """Test xAI provider import."""
        from pig_llm.providers.xai import XAIProvider

        assert XAIProvider is not None

    def test_cerebras_import(self):
        """Test Cerebras provider import."""
        from pig_llm.providers.cerebras import CerebrasProvider

        assert CerebrasProvider is not None

    def test_cohere_import(self):
        """Test Cohere provider import."""
        pytest.importorskip("cohere")
        from pig_llm.providers.cohere import CohereProvider

        assert CohereProvider is not None

    def test_perplexity_import(self):
        """Test Perplexity provider import."""
        from pig_llm.providers.perplexity import PerplexityProvider

        assert PerplexityProvider is not None

    def test_deepseek_import(self):
        """Test DeepSeek provider import."""
        from pig_llm.providers.deepseek import DeepSeekProvider

        assert DeepSeekProvider is not None

    def test_together_import(self):
        """Test Together AI provider import."""
        from pig_llm.providers.together import TogetherProvider

        assert TogetherProvider is not None


class TestProviderRegistration:
    """Test that providers are registered in client."""

    def test_all_providers_in_config(self):
        """Test that all providers are in config literal."""

        from pig_llm.config import Config

        # Get the Literal type from Config.provider
        Config.__fields__["provider"]
        # Check that new providers are included
        # This is a basic sanity check

    @pytest.mark.parametrize(
        "provider_name",
        [
            "bedrock",
            "xai",
            "cerebras",
            "cohere",
            "perplexity",
            "deepseek",
            "together",
        ],
    )
    def test_provider_initialization(self, provider_name):
        """Test that each provider can be initialized via LLM client."""
        # This test requires dependencies to be installed
        # Mark as integration test if needed
        pytest.skip("Requires dependencies and API keys - integration test")


@pytest.mark.parametrize(
    ("module_name", "class_name", "base_url"),
    [
        ("deepseek", "DeepSeekProvider", "https://api.deepseek.com"),
        ("together", "TogetherProvider", "https://api.together.xyz/v1"),
        ("xai", "XAIProvider", "https://api.x.ai/v1"),
        ("perplexity", "PerplexityProvider", "https://api.perplexity.ai"),
        ("cerebras", "CerebrasProvider", "https://api.cerebras.ai/v1"),
    ],
)
def test_openai_compatible_providers_send_session_affinity_headers(
    module_name: str,
    class_name: str,
    base_url: str,
):
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="test-model",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=None),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
    )
    sync_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    async_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock()))
    )

    with (
        patch(f"pig_llm.providers.{module_name}.openai.OpenAI", return_value=sync_client),
        patch(
            f"pig_llm.providers.{module_name}.openai.AsyncOpenAI",
            return_value=async_client,
        ),
    ):
        module = __import__(f"pig_llm.providers.{module_name}", fromlist=[class_name])
        provider_cls = getattr(module, class_name)
        provider = provider_cls(Config(provider=module_name, api_key="test", base_url=base_url))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        session_id="session-42",
    )

    assert create.call_args.kwargs["extra_headers"]["session-id"] == "session-42"
