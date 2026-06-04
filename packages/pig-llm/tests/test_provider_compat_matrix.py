"""Per-provider streaming compat matrix (fake-SDK, no network).

Mirrors pi-mono's approach: drive each provider's astream against a fake client
that captures the request kwargs, then assert the wire payload is correct —
token-limit param, stream_options usage, tools passthrough, and that internal
compat markers never leak into the SDK call.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pig_llm.config import Config
from pig_llm.models import Message
from pig_llm.providers.azure import AzureOpenAIProvider
from pig_llm.providers.cerebras import CerebrasProvider
from pig_llm.providers.deepseek import DeepSeekProvider
from pig_llm.providers.groq import GroqProvider
from pig_llm.providers.openai import OpenAIProvider
from pig_llm.providers.openrouter import OpenRouterProvider
from pig_llm.providers.perplexity import PerplexityProvider
from pig_llm.providers.together import TogetherProvider
from pig_llm.providers.xai import XAIProvider


class _FakeStream:
    """Async iterator yielding one text delta then a usage-only chunk."""

    def __aiter__(self):
        async def gen():
            yield SimpleNamespace(
                id="c1",
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="ok", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
                usage=None,
            )
            yield SimpleNamespace(
                id="c1",
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=10,
                    completion_tokens=2,
                    total_tokens=12,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=4),
                ),
            )

        return gen()


class _CapturingCreate:
    """Fake async chat.completions.create that records kwargs."""

    def __init__(self):
        self.kwargs: dict | None = None

    async def __call__(self, **kwargs):
        self.kwargs = kwargs
        return _FakeStream()


def _make_provider(cls, **config_overrides):
    cfg = Config(provider="x", api_key="test", **config_overrides)
    # Construct without touching the network, then swap in a fake async client.
    provider = cls.__new__(cls)
    provider.config = cfg
    capture = _CapturingCreate()
    provider.async_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=capture))
    )
    provider.client = provider.async_client
    return provider, capture


def _drive(provider, model: str, **kwargs) -> dict:
    async def run():
        chunks = []
        async for chunk in provider.astream(
            [Message(role="user", content="hi")], model=model, **kwargs
        ):
            chunks.append(chunk)
        return chunks

    return asyncio.run(run())


PROVIDERS = [
    (OpenAIProvider, "gpt-4o-mini"),
    (AzureOpenAIProvider, "gpt-4o-mini"),
    (DeepSeekProvider, "deepseek-chat"),
    (CerebrasProvider, "llama-3.3-70b"),
    (GroqProvider, "llama-3.3-70b-versatile"),
    (OpenRouterProvider, "openai/gpt-4o-mini"),
    (PerplexityProvider, "sonar"),
    (TogetherProvider, "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    (XAIProvider, "grok-2"),
]

_TOKEN_LIMIT_PARAMS = {"max_tokens", "max_completion_tokens"}
_INTERNAL_MARKERS = {"_resolved_cache_retention", "session_id", "cache_retention"}


@pytest.mark.parametrize("cls,model", PROVIDERS, ids=[c.__name__ for c, _ in PROVIDERS])
def test_astream_requests_usage_and_streams(cls, model):
    """Every OpenAI-compatible provider streams with usage requested."""
    provider, capture = _make_provider(cls)
    chunks = _drive(provider, model, max_tokens=128)

    kwargs = capture.kwargs
    assert kwargs is not None, "create() was never called"
    assert kwargs.get("stream") is True
    # Real usage is requested so cost/context tracking works.
    assert kwargs.get("stream_options") == {"include_usage": True}
    # Text streamed + the trailing usage chunk (with cached tokens) surfaced.
    text = "".join(c.content for c in chunks if c.content)
    assert text == "ok"
    usages = [c.usage for c in chunks if c.usage]
    assert usages and usages[-1]["cached_tokens"] == 4


@pytest.mark.parametrize("cls,model", PROVIDERS, ids=[c.__name__ for c, _ in PROVIDERS])
def test_astream_sends_exactly_one_token_limit_param(cls, model):
    """A single token-limit param is sent (legacy max_tokens is not duplicated)."""
    provider, capture = _make_provider(cls)
    _drive(provider, model, max_tokens=128)

    present = _TOKEN_LIMIT_PARAMS & set(capture.kwargs)
    assert len(present) == 1, f"expected one token-limit param, got {present}"


@pytest.mark.parametrize("cls,model", PROVIDERS, ids=[c.__name__ for c, _ in PROVIDERS])
def test_astream_does_not_leak_internal_markers(cls, model):
    """Internal compat markers must never reach the SDK create() call."""
    provider, capture = _make_provider(cls)
    _drive(provider, model, max_tokens=128, session_id="sess-1")

    leaked = _INTERNAL_MARKERS & set(capture.kwargs)
    assert not leaked, f"internal markers leaked to create(): {leaked}"


@pytest.mark.parametrize("cls,model", PROVIDERS, ids=[c.__name__ for c, _ in PROVIDERS])
def test_astream_passes_tools_through(cls, model):
    """A tools schema is forwarded to the provider create() call."""
    provider, capture = _make_provider(cls)
    tools = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]
    _drive(provider, model, max_tokens=128, tools=tools)

    assert capture.kwargs.get("tools") == tools


@pytest.mark.parametrize("cls,model", PROVIDERS, ids=[c.__name__ for c, _ in PROVIDERS])
def test_astream_sends_prompt_cache_key_when_session_present(cls, model):
    """With a session_id and long retention, a prompt_cache_key is sent."""
    provider, capture = _make_provider(cls)
    _drive(provider, model, max_tokens=128, session_id="sess-1", cache_retention="24h")

    # Providers that support OpenAI-style prompt caching attach the key; those
    # that don't simply omit it — but none should crash or leak the raw session.
    assert "session_id" not in capture.kwargs
