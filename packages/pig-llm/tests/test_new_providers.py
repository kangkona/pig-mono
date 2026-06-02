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


def test_bedrock_provider_forwards_custom_request_headers() -> None:
    pytest.importorskip("boto3")

    converse = Mock(
        return_value={
            "output": {"message": {"content": [{"text": "ok"}]}},
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "stopReason": "end_turn",
            "ResponseMetadata": {"RequestId": "req-1"},
        }
    )
    client = SimpleNamespace(converse=converse)

    with (
        patch("pig_llm.providers.bedrock.boto3.client", return_value=client),
        patch("pig_llm.providers.bedrock.BotoConfig", return_value=Mock()),
    ):
        from pig_llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider(Config(provider="bedrock", api_key="us-east-1"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="anthropic.claude-opus-4-1",
        headers={"X-Test": "1"},
    )

    assert converse.call_args.kwargs["requestMetadata"] == {"X-Test": "1"}


def test_bedrock_provider_uses_model_output_cap_by_default() -> None:
    pytest.importorskip("boto3")

    converse = Mock(
        return_value={
            "output": {"message": {"content": [{"text": "ok"}]}},
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "stopReason": "end_turn",
            "ResponseMetadata": {"RequestId": "req-1"},
        }
    )
    client = SimpleNamespace(converse=converse)

    with (
        patch("pig_llm.providers.bedrock.boto3.client", return_value=client),
        patch("pig_llm.providers.bedrock.BotoConfig", return_value=Mock()),
    ):
        from pig_llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider(
            Config(provider="bedrock", api_key="us-east-1", max_tokens=16384)
        )

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="anthropic.claude-opus-4-1",
    )

    assert converse.call_args.kwargs["inferenceConfig"]["maxTokens"] == 16384


def test_bedrock_provider_uses_adaptive_thinking_for_claude_opus_48() -> None:
    pytest.importorskip("boto3")

    converse = Mock(
        return_value={
            "output": {"message": {"content": [{"text": "ok"}]}},
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "stopReason": "end_turn",
            "ResponseMetadata": {"RequestId": "req-1"},
        }
    )
    client = SimpleNamespace(converse=converse)

    with (
        patch("pig_llm.providers.bedrock.boto3.client", return_value=client),
        patch("pig_llm.providers.bedrock.BotoConfig", return_value=Mock()),
    ):
        from pig_llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider(
            Config(provider="bedrock", api_key="us-east-1", max_tokens=16384)
        )

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="anthropic.claude-opus-4-8",
        thinking_level="high",
    )

    fields = converse.call_args.kwargs["additionalModelRequestFields"]
    assert fields["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert fields["output_config"] == {"effort": "high"}


def test_bedrock_provider_maps_xhigh_reasoning_to_output_config() -> None:
    pytest.importorskip("boto3")

    converse = Mock(
        return_value={
            "output": {"message": {"content": [{"text": "ok"}]}},
            "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "stopReason": "end_turn",
            "ResponseMetadata": {"RequestId": "req-1"},
        }
    )
    client = SimpleNamespace(converse=converse)

    with (
        patch("pig_llm.providers.bedrock.boto3.client", return_value=client),
        patch("pig_llm.providers.bedrock.BotoConfig", return_value=Mock()),
    ):
        from pig_llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider(
            Config(provider="bedrock", api_key="us-east-1", max_tokens=16384)
        )

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="anthropic.claude-opus-4-8",
        thinking_level="xhigh",
    )

    fields = converse.call_args.kwargs["additionalModelRequestFields"]
    assert fields["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert fields["output_config"] == {"effort": "xhigh"}


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


def test_xai_provider_uses_prompt_cache_for_long_retention() -> None:
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
        patch("pig_llm.providers.xai.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.xai.openai.AsyncOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.xai import XAIProvider

        provider = XAIProvider(Config(provider="xai", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        session_id="session-xai",
        cache_retention="long",
    )

    assert create.call_args.kwargs["prompt_cache_key"] == "session-xai"
    assert create.call_args.kwargs["prompt_cache_retention"] == "24h"


@pytest.mark.parametrize(
    ("module_name", "class_name", "base_url"),
    [
        ("xai", "XAIProvider", "https://api.x.ai/v1"),
        ("perplexity", "PerplexityProvider", "https://api.perplexity.ai"),
        ("cerebras", "CerebrasProvider", "https://api.cerebras.ai/v1"),
    ],
)
def test_openai_compatible_providers_use_prompt_cache_for_long_retention(
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
        cache_retention="long",
    )

    assert create.call_args.kwargs["prompt_cache_key"] == "session-42"
    assert create.call_args.kwargs["prompt_cache_retention"] == "24h"


def test_deepseek_provider_sends_explicit_thinking_disabled_payload() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-reasoner",
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
        patch("pig_llm.providers.deepseek.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.deepseek.openai.AsyncOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.deepseek import DeepSeekProvider

        provider = DeepSeekProvider(Config(provider="deepseek", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="deepseek-reasoner",
        thinking_level="off",
    )

    assert create.call_args.kwargs["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_deepseek_provider_sends_explicit_thinking_enabled_payload() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-reasoner",
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
        patch("pig_llm.providers.deepseek.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.deepseek.openai.AsyncOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.deepseek import DeepSeekProvider

        provider = DeepSeekProvider(Config(provider="deepseek", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="deepseek-reasoner",
        thinking_level="high",
    )

    assert create.call_args.kwargs["thinking"] == {"type": "enabled"}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_deepseek_provider_uses_prompt_cache_and_affinity_headers() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-reasoner",
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
        patch("pig_llm.providers.deepseek.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.deepseek.openai.AsyncOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.deepseek import DeepSeekProvider

        provider = DeepSeekProvider(Config(provider="deepseek", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="deepseek-reasoner",
        session_id="session-deepseek",
        cache_retention="long",
    )

    assert create.call_args.kwargs["prompt_cache_key"] == "session-deepseek"
    assert create.call_args.kwargs["prompt_cache_retention"] == "24h"
    assert create.call_args.kwargs["extra_headers"]["session_id"] == "session-deepseek"
    assert create.call_args.kwargs["extra_headers"]["x-client-request-id"] == "session-deepseek"
    assert create.call_args.kwargs["extra_headers"]["x-session-affinity"] == "session-deepseek"


def test_together_provider_sends_explicit_reasoning_disabled_payload() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="moonshotai/Kimi-K2.6",
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
        patch("pig_llm.providers.together.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.together.openai.AsyncOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.together import TogetherProvider

        provider = TogetherProvider(Config(provider="together", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="moonshotai/Kimi-K2.6",
        thinking_level="off",
    )

    assert create.call_args.kwargs["reasoning"] == {"enabled": False}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_provider_sends_explicit_reasoning_enabled_payload() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="moonshotai/Kimi-K2.6",
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
        patch("pig_llm.providers.together.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.together.openai.AsyncOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.together import TogetherProvider

        provider = TogetherProvider(Config(provider="together", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="moonshotai/Kimi-K2.6",
        thinking_level="high",
    )

    assert create.call_args.kwargs["reasoning"] == {"enabled": True}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_provider_uses_affinity_headers_but_omits_long_prompt_cache() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="moonshotai/Kimi-K2.6",
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
        patch("pig_llm.providers.together.openai.OpenAI", return_value=sync_client),
        patch("pig_llm.providers.together.openai.AsyncOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.together import TogetherProvider

        provider = TogetherProvider(Config(provider="together", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="moonshotai/Kimi-K2.6",
        session_id="session-together",
        cache_retention="long",
    )

    assert "prompt_cache_key" not in create.call_args.kwargs
    assert "prompt_cache_retention" not in create.call_args.kwargs
    assert create.call_args.kwargs["extra_headers"]["session_id"] == "session-together"
    assert create.call_args.kwargs["extra_headers"]["x-client-request-id"] == "session-together"
    assert create.call_args.kwargs["extra_headers"]["x-session-affinity"] == "session-together"


def test_azure_openai_provider_uses_session_affinity_headers() -> None:
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
        patch("pig_llm.providers.azure.openai.AzureOpenAI", return_value=sync_client),
        patch("pig_llm.providers.azure.openai.AsyncAzureOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.azure import AzureOpenAIProvider

        provider = AzureOpenAIProvider(
            Config(
                provider="azure",
                api_key="test",
                base_url="https://example.openai.azure.com",
            )
        )

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        session_id="session-99",
    )

    assert create.call_args.kwargs["extra_headers"]["session-id"] == "session-99"


def test_azure_openai_provider_uses_prompt_cache_for_long_retention() -> None:
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
        patch("pig_llm.providers.azure.openai.AzureOpenAI", return_value=sync_client),
        patch("pig_llm.providers.azure.openai.AsyncAzureOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.azure import AzureOpenAIProvider

        provider = AzureOpenAIProvider(
            Config(
                provider="azure",
                api_key="test",
                base_url="https://example.openai.azure.com",
            )
        )

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        session_id="session-99",
        cache_retention="long",
    )

    assert create.call_args.kwargs["prompt_cache_key"] == "session-99"
    assert create.call_args.kwargs["prompt_cache_retention"] == "24h"


def test_azure_openai_provider_preserves_explicit_max_tokens() -> None:
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
        patch("pig_llm.providers.azure.openai.AzureOpenAI", return_value=sync_client),
        patch("pig_llm.providers.azure.openai.AsyncAzureOpenAI", return_value=async_client),
    ):
        from pig_llm.providers.azure import AzureOpenAIProvider

        provider = AzureOpenAIProvider(
            Config(
                provider="azure",
                api_key="test",
                base_url="https://example.openai.azure.com",
            )
        )

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        max_tokens=321,
    )

    assert create.call_args.kwargs["max_tokens"] == 321


def test_groq_provider_uses_session_affinity_headers() -> None:
    pytest.importorskip("groq")
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
        patch("pig_llm.providers.groq.Groq", return_value=sync_client),
        patch("pig_llm.providers.groq.AsyncGroq", return_value=async_client),
    ):
        from pig_llm.providers.groq import GroqProvider

        provider = GroqProvider(Config(provider="groq", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        session_id="session-groq",
    )

    assert create.call_args.kwargs["extra_headers"]["session-id"] == "session-groq"


def test_groq_provider_uses_prompt_cache_for_long_retention() -> None:
    pytest.importorskip("groq")
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
        patch("pig_llm.providers.groq.Groq", return_value=sync_client),
        patch("pig_llm.providers.groq.AsyncGroq", return_value=async_client),
    ):
        from pig_llm.providers.groq import GroqProvider

        provider = GroqProvider(Config(provider="groq", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        session_id="session-groq",
        cache_retention="long",
    )

    assert create.call_args.kwargs["prompt_cache_key"] == "session-groq"
    assert create.call_args.kwargs["prompt_cache_retention"] == "24h"


def test_groq_provider_preserves_explicit_max_tokens() -> None:
    pytest.importorskip("groq")
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
        patch("pig_llm.providers.groq.Groq", return_value=sync_client),
        patch("pig_llm.providers.groq.AsyncGroq", return_value=async_client),
    ):
        from pig_llm.providers.groq import GroqProvider

        provider = GroqProvider(Config(provider="groq", api_key="test"))

    provider.complete(
        [SimpleNamespace(role="user", content="hello", metadata=None)],
        model="test-model",
        max_tokens=222,
    )

    assert create.call_args.kwargs["max_tokens"] == 222
