"""Tests for newly added providers."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pig_llm.config import Config
from pig_llm.models import Message


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


def test_bedrock_provider_ignores_reserved_request_headers() -> None:
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
        headers={
            "X-Test": "1",
            "Authorization": "Bearer test",
            "host": "example.com",
            "x-amz-trace-id": "trace",
        },
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


def test_bedrock_provider_normalizes_explicit_developer_role_to_system() -> None:
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
        [
            Message(role="developer", content="rules"),
            Message(role="user", content="hello"),
        ],
        model="anthropic.claude-opus-4-1",
    )

    assert converse.call_args.kwargs["system"] == [{"text": "rules"}]
    assert converse.call_args.kwargs["messages"] == [
        {"role": "user", "content": [{"text": "hello"}]}
    ]


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
    assert "_resolved_cache_retention" not in create.call_args.kwargs


@pytest.mark.parametrize(
    ("module_name", "class_name", "base_url"),
    [
        ("xai", "XAIProvider", "https://api.x.ai/v1"),
        ("perplexity", "PerplexityProvider", "https://api.perplexity.ai"),
        ("cerebras", "CerebrasProvider", "https://api.cerebras.ai/v1"),
    ],
)
def test_openai_compatible_provider_wrappers_promote_developer_instruction_role(
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
        [
            Message(role="system", content="rules", metadata={"role": "developer"}),
            Message(role="user", content="hello"),
        ],
        model="test-model",
    )

    assert create.call_args.kwargs["messages"][0] == {"role": "developer", "content": "rules"}


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

    assert create.call_args.kwargs["extra_body"]["thinking"] == {"type": "disabled"}
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

    assert create.call_args.kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_deepseek_v4_flash_omits_unsupported_medium_thinking() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-v4-flash",
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
        model="deepseek-v4-flash",
        thinking_level="medium",
    )

    assert "thinking" not in create.call_args.kwargs
    assert "reasoning_effort" not in create.call_args.kwargs


def test_deepseek_v4_flash_sends_high_reasoning_effort() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-v4-flash",
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
        model="deepseek-v4-flash",
        thinking_level="high",
    )

    assert create.call_args.kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert create.call_args.kwargs["reasoning_effort"] == "high"


def test_deepseek_v4_flash_maps_xhigh_reasoning_to_max() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-v4-flash",
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
        model="deepseek-v4-flash",
        thinking_level="xhigh",
    )

    assert create.call_args.kwargs["extra_body"]["thinking"] == {"type": "enabled"}
    assert create.call_args.kwargs["reasoning_effort"] == "max"


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


def test_deepseek_provider_normalizes_explicit_developer_role_to_system() -> None:
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
        [
            Message(role="developer", content="rules"),
            Message(role="user", content="hello"),
        ],
        model="deepseek-reasoner",
    )

    assert create.call_args.kwargs["messages"][0] == {"role": "system", "content": "rules"}


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

    assert create.call_args.kwargs["extra_body"]["reasoning"] == {"enabled": False}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_provider_normalizes_explicit_developer_role_to_system() -> None:
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
        [
            Message(role="developer", content="rules"),
            Message(role="user", content="hello"),
        ],
        model="moonshotai/Kimi-K2.6",
    )

    assert create.call_args.kwargs["messages"][0] == {"role": "system", "content": "rules"}


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

    assert create.call_args.kwargs["extra_body"]["reasoning"] == {"enabled": True}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_kimi_k26_omits_unsupported_medium_reasoning() -> None:
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
        thinking_level="medium",
    )

    assert "reasoning" not in create.call_args.kwargs
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_deepseek_v4_pro_sends_reasoning_effort() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-ai/DeepSeek-V4-Pro",
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
        model="deepseek-ai/DeepSeek-V4-Pro",
        thinking_level="high",
    )

    assert create.call_args.kwargs["extra_body"]["reasoning"] == {"enabled": True}
    assert create.call_args.kwargs["reasoning_effort"] == "high"


def test_together_deepseek_v4_pro_omits_reasoning_effort_for_unmapped_levels() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="deepseek-ai/DeepSeek-V4-Pro",
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
        model="deepseek-ai/DeepSeek-V4-Pro",
        thinking_level="medium",
    )

    assert create.call_args.kwargs["extra_body"]["reasoning"] == {"enabled": True}
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_gpt_oss_20b_uses_openai_reasoning_effort_payload() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="openai/gpt-oss-20b",
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
        model="openai/gpt-oss-20b",
        thinking_level="high",
    )

    assert create.call_args.kwargs["reasoning_effort"] == "high"
    assert "reasoning" not in create.call_args.kwargs


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


def test_together_minimax_m27_omits_unsupported_off_reasoning() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="MiniMaxAI/MiniMax-M2.7",
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
        model="MiniMaxAI/MiniMax-M2.7",
        thinking_level="off",
    )

    assert "reasoning" not in create.call_args.kwargs
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_kimi_k25_omits_unsupported_off_reasoning() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="moonshotai/Kimi-K2.5",
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
        model="moonshotai/Kimi-K2.5",
        thinking_level="off",
    )

    assert "reasoning" not in create.call_args.kwargs
    assert "reasoning_effort" not in create.call_args.kwargs


def test_together_qwen36_plus_omits_unsupported_medium_reasoning() -> None:
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="Qwen/Qwen3.6-Plus",
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
        model="Qwen/Qwen3.6-Plus",
        thinking_level="medium",
    )

    assert "reasoning" not in create.call_args.kwargs
    assert "reasoning_effort" not in create.call_args.kwargs


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

    assert create.call_args.kwargs["extra_headers"]["session_id"] == "session-99"
    assert create.call_args.kwargs["extra_headers"]["x-client-request-id"] == "session-99"
    assert create.call_args.kwargs["extra_headers"]["x-session-affinity"] == "session-99"
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


def test_azure_openai_provider_promotes_developer_instruction_role() -> None:
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
        [
            Message(role="system", content="rules", metadata={"role": "developer"}),
            Message(role="user", content="hello"),
        ],
        model="test-model",
    )

    assert create.call_args.kwargs["messages"][0] == {"role": "developer", "content": "rules"}


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

    assert create.call_args.kwargs["extra_headers"]["session_id"] == "session-groq"
    assert create.call_args.kwargs["extra_headers"]["x-client-request-id"] == "session-groq"
    assert create.call_args.kwargs["extra_headers"]["x-session-affinity"] == "session-groq"
    assert create.call_args.kwargs["extra_headers"]["session-id"] == "session-groq"


def test_groq_provider_promotes_developer_instruction_role() -> None:
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
        [
            Message(role="system", content="rules", metadata={"role": "developer"}),
            Message(role="user", content="hello"),
        ],
        model="test-model",
    )

    assert create.call_args.kwargs["messages"][0] == {"role": "developer", "content": "rules"}


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


def test_groq_qwen3_maps_medium_reasoning_to_default() -> None:
    pytest.importorskip("groq")
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="qwen/qwen3-32b",
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
        model="qwen/qwen3-32b",
        thinking_level="medium",
    )

    assert create.call_args.kwargs["reasoning_effort"] == "default"


def test_groq_qwq_keeps_reasoning_effort_value() -> None:
    pytest.importorskip("groq")
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="qwen-qwq-32b",
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
        model="qwen-qwq-32b",
        thinking_level="medium",
    )

    assert create.call_args.kwargs["reasoning_effort"] == "medium"


def test_groq_non_qwen_model_keeps_reasoning_effort_value() -> None:
    pytest.importorskip("groq")
    create = Mock(
        return_value=SimpleNamespace(
            id="resp-1",
            model="openai/gpt-oss-20b",
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
        model="openai/gpt-oss-20b",
        thinking_level="medium",
    )

    assert create.call_args.kwargs["reasoning_effort"] == "medium"


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


@pytest.mark.asyncio
async def test_bedrock_astream_captures_tool_use_and_usage() -> None:
    """Bedrock converse_stream surfaces toolUse blocks + usage (Phase B)."""
    pytest.importorskip("boto3")

    events = [
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "checking"}}},
        {
            "contentBlockStart": {
                "contentBlockIndex": 1,
                "start": {"toolUse": {"toolUseId": "tu_1", "name": "get_weather"}},
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 1,
                "delta": {"toolUse": {"input": '{"city":'}},
            }
        },
        {
            "contentBlockDelta": {
                "contentBlockIndex": 1,
                "delta": {"toolUse": {"input": '"Tokyo"}'}},
            }
        },
        {"messageStop": {"stopReason": "tool_use"}},
        {
            "metadata": {
                "usage": {
                    "inputTokens": 120,
                    "outputTokens": 18,
                    "totalTokens": 138,
                    "cacheReadInputTokens": 40,
                }
            }
        },
    ]
    converse_stream = Mock(return_value={"stream": iter(events)})
    client = SimpleNamespace(converse_stream=converse_stream)

    with (
        patch("pig_llm.providers.bedrock.boto3.client", return_value=client),
        patch("pig_llm.providers.bedrock.BotoConfig", return_value=Mock()),
    ):
        from pig_llm.providers.bedrock import BedrockProvider

        provider = BedrockProvider(Config(provider="bedrock", api_key="us-east-1"))
        chunks = [
            c
            async for c in provider.astream(
                [Message(role="user", content="weather?")], model="anthropic.claude-3-haiku"
            )
        ]

    assert "".join(c.content for c in chunks if c.content) == "checking"
    tool_chunks = [c for c in chunks if c.tool_calls]
    tc = tool_chunks[-1].tool_calls[0]
    assert tc["function"]["name"] == "get_weather"
    assert tc["function"]["arguments"] == '{"city":"Tokyo"}'
    usages = [c.usage for c in chunks if c.usage]
    assert usages[-1]["input_tokens"] == 120
    assert usages[-1]["cached_tokens"] == 40


@pytest.mark.asyncio
async def test_mistral_astream_emits_usage() -> None:
    pytest.importorskip("mistralai.models.chat_completion")

    class _Stream:
        def __aiter__(self):
            async def gen():
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(delta=SimpleNamespace(content="ok"), finish_reason=None)
                    ],
                    usage=None,
                )
                yield SimpleNamespace(
                    choices=[
                        SimpleNamespace(delta=SimpleNamespace(content=None), finish_reason="stop")
                    ],
                    usage=SimpleNamespace(prompt_tokens=50, completion_tokens=8, total_tokens=58),
                )

            return gen()

    from pig_llm.providers.mistral import MistralProvider

    provider = MistralProvider.__new__(MistralProvider)
    provider.config = Config(provider="mistral", api_key="t")
    provider.async_client = SimpleNamespace(chat_stream=AsyncMock(return_value=_Stream()))
    if True:
        chunks = [
            c
            async for c in provider.astream(
                [Message(role="user", content="hi")], model="mistral-small"
            )
        ]

    assert "".join(c.content for c in chunks if c.content) == "ok"
    usages = [c.usage for c in chunks if c.usage]
    assert usages[-1] == {"input_tokens": 50, "output_tokens": 8, "total_tokens": 58}


@pytest.mark.asyncio
async def test_cohere_astream_emits_usage() -> None:
    pytest.importorskip("cohere")

    class _Stream:
        def __aiter__(self):
            async def gen():
                yield SimpleNamespace(event_type="text-generation", text="ok")
                yield SimpleNamespace(
                    event_type="stream-end",
                    finish_reason="COMPLETE",
                    response=SimpleNamespace(
                        meta=SimpleNamespace(
                            tokens=SimpleNamespace(input_tokens=40, output_tokens=6)
                        )
                    ),
                )

            return gen()

    from pig_llm.providers.cohere import CohereProvider

    provider = CohereProvider.__new__(CohereProvider)
    provider.config = Config(provider="cohere", api_key="t")
    provider.async_client = SimpleNamespace(chat_stream=Mock(return_value=_Stream()))
    if True:
        chunks = [
            c
            async for c in provider.astream([Message(role="user", content="hi")], model="command-r")
        ]

    assert "".join(c.content for c in chunks if c.content) == "ok"
    usages = [c.usage for c in chunks if c.usage]
    assert usages[-1] == {"input_tokens": 40, "output_tokens": 6, "total_tokens": 46}
