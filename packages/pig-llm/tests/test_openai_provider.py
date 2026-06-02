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


def _provider_with_clients(
    sync_create: Mock, async_create: AsyncMock, config: Config | None = None
) -> OpenAIProvider:
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
        return OpenAIProvider(config or Config(api_key="test-key"))


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


def test_explicit_session_header_overrides_generated_session_id_header() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.2",
        session_id="session-123",
        headers={"session-id": "override-session"},
    )

    assert sync_create.call_args.kwargs["extra_headers"]["session-id"] == "override-session"


def test_native_openai_uses_session_id_as_prompt_cache_key() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.2",
        session_id="session-123",
    )

    assert sync_create.call_args.kwargs["prompt_cache_key"] == "session-123"
    assert "prompt_cache_retention" not in sync_create.call_args.kwargs


def test_native_openai_sets_prompt_cache_retention_for_long_cache() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.2",
        session_id="session-123",
        cache_retention="long",
    )

    assert sync_create.call_args.kwargs["prompt_cache_key"] == "session-123"
    assert sync_create.call_args.kwargs["prompt_cache_retention"] == "24h"


def test_native_openai_uses_environment_default_for_long_cache_retention(monkeypatch) -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    monkeypatch.setenv("PI_CACHE_RETENTION", "long")

    provider.complete(
        _messages(),
        model="gpt-5.2",
        session_id="session-123",
    )

    assert sync_create.call_args.kwargs["prompt_cache_key"] == "session-123"
    assert sync_create.call_args.kwargs["prompt_cache_retention"] == "24h"


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


def test_native_openai_maps_thinking_level_to_reasoning_effort() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.2",
        thinking_level="high",
    )

    assert sync_create.call_args.kwargs["reasoning_effort"] == "high"
    assert "thinking" not in sync_create.call_args.kwargs


def test_native_openai_promotes_developer_metadata_role() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        [
            Message(role="system", content="rules", metadata={"role": "developer"}),
            Message(role="user", content="hi"),
        ],
        model="gpt-5.2",
    )

    messages = sync_create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "developer", "content": "rules"}


def test_native_openai_maps_thinking_off_to_none_reasoning_effort() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.2",
        thinking_level="off",
    )

    assert sync_create.call_args.kwargs["reasoning_effort"] == "none"
    assert "thinking" not in sync_create.call_args.kwargs


def test_native_openai_gpt_55_pro_omits_unsupported_minimal_reasoning() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.5-pro",
        thinking_level="minimal",
    )

    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_native_openai_gpt_55_omits_unsupported_minimal_reasoning() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(sync_create, AsyncMock())

    provider.complete(
        _messages(),
        model="gpt-5.5",
        thinking_level="minimal",
    )

    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_qwen_base_url_uses_enable_thinking_toggle() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="qwen/qwen3-coder",
        thinking_level="high",
    )

    assert sync_create.call_args.kwargs["enable_thinking"] is True
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_qwen_chat_template_compat_uses_chat_template_kwargs() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://local-qwen-gateway.example/v1",
            compat_mode="qwen-chat-template",
        ),
    )

    provider.complete(
        _messages(),
        model="qwen/qwen3-coder",
        thinking_level="high",
    )

    assert sync_create.call_args.kwargs["chat_template_kwargs"] == {
        "enable_thinking": True,
        "preserve_thinking": True,
    }
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_openrouter_compat_uses_nested_reasoning_payload() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://router.example/v1",
            compat_mode="openrouter",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek/deepseek-r1",
        thinking_level="high",
    )

    assert sync_create.call_args.kwargs["reasoning"] == {"effort": "high"}
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_openrouter_compat_gpt_55_pro_omits_unsupported_low_reasoning() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://router.example/v1",
            compat_mode="openrouter",
        ),
    )

    provider.complete(
        _messages(),
        model="openai/gpt-5.5-pro",
        thinking_level="low",
    )

    assert "reasoning" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_openrouter_compat_deepseek_v4_flash_omits_unsupported_medium_reasoning() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://router.example/v1",
            compat_mode="openrouter",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek/deepseek-v4-flash",
        thinking_level="medium",
    )

    assert "reasoning" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_openrouter_compat_deepseek_v4_flash_keeps_xhigh_reasoning() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://router.example/v1",
            compat_mode="openrouter",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek/deepseek-v4-flash",
        thinking_level="xhigh",
    )

    assert sync_create.call_args.kwargs["reasoning"] == {"effort": "xhigh"}
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_openrouter_compat_uses_max_tokens_field() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://router.example/v1",
            compat_mode="openrouter",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek/deepseek-r1",
        max_tokens=321,
    )

    assert sync_create.call_args.kwargs["max_tokens"] == 321
    assert "max_completion_tokens" not in sync_create.call_args.kwargs


def test_explicit_openrouter_compat_adds_session_affinity_headers() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://router.example/v1",
            compat_mode="openrouter",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek/deepseek-r1",
        session_id="session-affinity",
    )

    assert sync_create.call_args.kwargs["extra_headers"]["session_id"] == "session-affinity"
    assert (
        sync_create.call_args.kwargs["extra_headers"]["x-client-request-id"] == "session-affinity"
    )
    assert sync_create.call_args.kwargs["extra_headers"]["x-session-affinity"] == "session-affinity"


def test_custom_zai_base_url_disables_thinking_when_off() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://api.z.ai/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="glm-4.5-air",
        thinking_level="off",
    )

    assert sync_create.call_args.kwargs["enable_thinking"] is False
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_deepseek_compat_uses_thinking_object() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://reasoner.example/v1",
            compat_mode="deepseek",
        ),
    )

    provider.complete(
        _messages(),
        model="custom-reasoner",
        thinking_level="off",
    )

    assert sync_create.call_args.kwargs["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_deepseek_compat_uses_max_tokens_field() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://reasoner.example/v1",
            compat_mode="deepseek",
        ),
    )

    provider.complete(
        _messages(),
        model="custom-reasoner",
        max_tokens=222,
    )

    assert sync_create.call_args.kwargs["max_tokens"] == 222
    assert "max_completion_tokens" not in sync_create.call_args.kwargs


def test_explicit_deepseek_compat_deepseek_v4_flash_omits_unsupported_medium_thinking() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://reasoner.example/v1",
            compat_mode="deepseek",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek-v4-flash",
        thinking_level="medium",
    )

    assert "thinking" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_string_thinking_compat_uses_string_payload() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://custom-kimi.example/v1",
            compat_mode="string-thinking",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        thinking_level="off",
    )

    assert sync_create.call_args.kwargs["thinking"] == "none"
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_together_compat_uses_max_tokens_field() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://together-gateway.example/v1",
            compat_mode="together",
        ),
    )

    provider.complete(
        _messages(),
        model="moonshotai/Kimi-K2.6",
        max_tokens=111,
    )

    assert sync_create.call_args.kwargs["max_tokens"] == 111
    assert "max_completion_tokens" not in sync_create.call_args.kwargs


def test_explicit_together_compat_omits_prompt_cache_retention() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://together-gateway.example/v1",
            compat_mode="together",
        ),
    )

    provider.complete(
        _messages(),
        model="moonshotai/Kimi-K2.6",
        session_id="session-123",
        cache_retention="long",
    )

    assert "prompt_cache_key" not in sync_create.call_args.kwargs
    assert "prompt_cache_retention" not in sync_create.call_args.kwargs


def test_explicit_moonshot_compat_uses_max_tokens_field() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://api.moonshot.ai/v1",
            compat_mode="moonshot",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        max_tokens=444,
    )

    assert sync_create.call_args.kwargs["max_tokens"] == 444
    assert "max_completion_tokens" not in sync_create.call_args.kwargs


def test_moonshot_base_url_auto_detects_moonshot_compat() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://api.moonshot.ai/v1",
        ),
    )

    provider.complete(
        [
            Message(role="system", content="rules", metadata={"role": "developer"}),
            Message(role="user", content="hi"),
        ],
        model="kimi-k2.6",
        session_id="session-123",
        cache_retention="long",
        max_tokens=444,
        thinking_level="high",
    )

    messages = sync_create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "rules"}
    assert sync_create.call_args.kwargs["max_tokens"] == 444
    assert "max_completion_tokens" not in sync_create.call_args.kwargs
    assert "prompt_cache_key" not in sync_create.call_args.kwargs
    assert "prompt_cache_retention" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_moonshot_compat_omits_prompt_cache_retention() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://api.moonshot.ai/v1",
            compat_mode="moonshot",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        session_id="session-123",
        cache_retention="long",
    )

    assert "prompt_cache_key" not in sync_create.call_args.kwargs
    assert "prompt_cache_retention" not in sync_create.call_args.kwargs


def test_explicit_moonshot_compat_keeps_developer_metadata_as_system() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://api.moonshot.ai/v1",
            compat_mode="moonshot",
        ),
    )

    provider.complete(
        [
            Message(role="system", content="rules", metadata={"role": "developer"}),
            Message(role="user", content="hi"),
        ],
        model="kimi-k2.6",
        thinking_level="high",
    )

    messages = sync_create.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "rules"}
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_explicit_moonshot_compat_omits_session_affinity_headers_when_cache_is_none() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://api.moonshot.ai/v1",
            compat_mode="moonshot",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        session_id="session-123",
        cache_retention="none",
    )

    extra_headers = sync_create.call_args.kwargs["extra_headers"]
    assert extra_headers["session-id"] == "session-123"
    assert "session_id" not in extra_headers
    assert "x-client-request-id" not in extra_headers
    assert "x-session-affinity" not in extra_headers


def test_explicit_together_compat_supports_deepseek_v4_reasoning_effort() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            compat_mode="together",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek-ai/DeepSeek-V4-Pro",
        thinking_level="high",
    )

    assert sync_create.call_args.kwargs["reasoning"] == {"enabled": True}
    assert sync_create.call_args.kwargs["reasoning_effort"] == "high"


def test_custom_opencode_go_kimi_uses_thinking_object_when_disabled() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/go/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        thinking_level="off",
    )

    assert sync_create.call_args.kwargs["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_go_kimi_uses_thinking_object_when_enabled() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/go/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        thinking_level="high",
    )

    assert sync_create.call_args.kwargs["thinking"] == {"type": "enabled"}
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_go_kimi_omits_unsupported_minimal_thinking() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/go/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        thinking_level="minimal",
    )

    assert "thinking" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_go_kimi_omits_unsupported_medium_thinking() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/go/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="kimi-k2.6",
        thinking_level="medium",
    )

    assert "thinking" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_go_deepseek_v4_flash_omits_unsupported_medium_thinking() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/go/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek-v4-flash",
        thinking_level="medium",
    )

    assert "thinking" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_zen_grok_build_omits_reasoning_effort() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="grok-build-0.1",
        thinking_level="high",
    )

    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_zen_grok_build_omits_unsupported_off_thinking() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="grok-build-0.1",
        thinking_level="off",
    )

    assert "thinking" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_zen_deepseek_v4_flash_omits_unsupported_medium_thinking() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek-v4-flash",
        thinking_level="medium",
    )

    assert "thinking" not in sync_create.call_args.kwargs
    assert "reasoning_effort" not in sync_create.call_args.kwargs


def test_custom_opencode_zen_deepseek_v4_flash_maps_xhigh_reasoning_to_max() -> None:
    sync_create = Mock(return_value=_completion_response())
    provider = _provider_with_clients(
        sync_create,
        AsyncMock(),
        Config(
            provider="openai",
            api_key="test-key",
            base_url="https://opencode.ai/zen/v1",
        ),
    )

    provider.complete(
        _messages(),
        model="deepseek-v4-flash",
        thinking_level="xhigh",
    )

    assert sync_create.call_args.kwargs["thinking"] == {"type": "enabled"}
    assert sync_create.call_args.kwargs["reasoning_effort"] == "max"


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
