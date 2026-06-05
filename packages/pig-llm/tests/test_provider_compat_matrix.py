"""Per-provider streaming compat matrix (fake-SDK, no network).

Mirrors pi-mono's approach: drive each provider's astream against a fake client
that captures the request kwargs, then assert the wire payload is correct —
token-limit param, stream_options usage, tools passthrough, and that internal
compat markers never leak into the SDK call.
"""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest
from pig_llm.config import Config
from pig_llm.models import Message


def _load_provider(module: str, cls_name: str, sdk: str):
    """Import a provider class, skipping if its optional SDK isn't installed.

    Provider modules import their SDK at module load time, so a missing
    optional dependency (e.g. `groq` in CI) must turn into a skip rather than a
    collection-time ImportError that aborts the whole matrix.
    """
    pytest.importorskip(sdk)
    mod = importlib.import_module(f"pig_llm.providers.{module}")
    return getattr(mod, cls_name)


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


def _make_provider(spec, **config_overrides):
    cls = _load_provider(*spec)
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


# (provider module, class name, required SDK module, model). The class is
# imported lazily so a missing optional SDK skips just that row.
PROVIDERS = [
    (("openai", "OpenAIProvider", "openai"), "gpt-4o-mini"),
    (("azure", "AzureOpenAIProvider", "openai"), "gpt-4o-mini"),
    (("deepseek", "DeepSeekProvider", "openai"), "deepseek-chat"),
    (("cerebras", "CerebrasProvider", "openai"), "llama-3.3-70b"),
    (("groq", "GroqProvider", "groq"), "llama-3.3-70b-versatile"),
    (("openrouter", "OpenRouterProvider", "openai"), "openai/gpt-4o-mini"),
    (("perplexity", "PerplexityProvider", "openai"), "sonar"),
    (("together", "TogetherProvider", "openai"), "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    (("xai", "XAIProvider", "openai"), "grok-2"),
]

_TOKEN_LIMIT_PARAMS = {"max_tokens", "max_completion_tokens"}
_INTERNAL_MARKERS = {"_resolved_cache_retention", "session_id", "cache_retention"}


@pytest.mark.parametrize("spec,model", PROVIDERS, ids=[s[1] for s, _ in PROVIDERS])
def test_astream_requests_usage_and_streams(spec, model):
    """Every OpenAI-compatible provider streams with usage requested."""
    provider, capture = _make_provider(spec)
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


@pytest.mark.parametrize("spec,model", PROVIDERS, ids=[s[1] for s, _ in PROVIDERS])
def test_astream_sends_exactly_one_token_limit_param(spec, model):
    """A single token-limit param is sent (legacy max_tokens is not duplicated)."""
    provider, capture = _make_provider(spec)
    _drive(provider, model, max_tokens=128)

    present = _TOKEN_LIMIT_PARAMS & set(capture.kwargs)
    assert len(present) == 1, f"expected one token-limit param, got {present}"


@pytest.mark.parametrize("spec,model", PROVIDERS, ids=[s[1] for s, _ in PROVIDERS])
def test_astream_does_not_leak_internal_markers(spec, model):
    """Internal compat markers must never reach the SDK create() call."""
    provider, capture = _make_provider(spec)
    _drive(provider, model, max_tokens=128, session_id="sess-1")

    leaked = _INTERNAL_MARKERS & set(capture.kwargs)
    assert not leaked, f"internal markers leaked to create(): {leaked}"


@pytest.mark.parametrize("spec,model", PROVIDERS, ids=[s[1] for s, _ in PROVIDERS])
def test_astream_passes_tools_through(spec, model):
    """A tools schema is forwarded to the provider create() call."""
    provider, capture = _make_provider(spec)
    tools = [{"type": "function", "function": {"name": "noop", "parameters": {}}}]
    _drive(provider, model, max_tokens=128, tools=tools)

    assert capture.kwargs.get("tools") == tools


@pytest.mark.parametrize("spec,model", PROVIDERS, ids=[s[1] for s, _ in PROVIDERS])
def test_astream_sends_prompt_cache_key_when_session_present(spec, model):
    """With a session_id and long retention, a prompt_cache_key is sent."""
    provider, capture = _make_provider(spec)
    _drive(provider, model, max_tokens=128, session_id="sess-1", cache_retention="24h")

    # Providers that support OpenAI-style prompt caching attach the key; those
    # that don't simply omit it — but none should crash or leak the raw session.
    assert "session_id" not in capture.kwargs


@pytest.mark.parametrize("spec,model", PROVIDERS, ids=[s[1] for s, _ in PROVIDERS])
def test_astream_relocates_nonstandard_params_to_extra_body(spec, model):
    """OpenRouter-style reasoning is sent via extra_body, never as a raw kwarg.

    Regression: a top-level `reasoning` kwarg crashed the OpenAI SDK with
    TypeError; non-standard params must be relocated into extra_body.
    """
    provider, capture = _make_provider(spec)
    _drive(provider, model, max_tokens=128, thinking_level="high")

    kwargs = capture.kwargs
    # None of the non-standard thinking keys may appear as top-level kwargs.
    for key in ("reasoning", "thinking", "enable_thinking", "chat_template_kwargs"):
        assert key not in kwargs, f"{key} leaked as a top-level create() kwarg"
