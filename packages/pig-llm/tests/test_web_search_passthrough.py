"""Native web-search passthrough (Anthropic MVP).

The LLM client carries a provider-neutral ``enable_web_search`` intent and only
forwards it to providers that understand it; the Anthropic provider translates
it into its native server-side ``web_search`` tool. These tests drive the full
client -> provider path against fake SDK clients (no network).
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pig_llm import LLM
from pig_llm.models import Message

NATIVE = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}


def _anthropic_response() -> SimpleNamespace:
    return SimpleNamespace(
        id="msg_1",
        model="claude-opus-4-8",
        content=[SimpleNamespace(type="text", text="ok")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )


def _openai_response() -> SimpleNamespace:
    return SimpleNamespace(
        id="chatcmpl-1",
        model="gpt-4o-mini",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def _anthropic_llm(create: Mock, enable_web_search: bool, **extra) -> LLM:
    pytest.importorskip("anthropic")
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    with (
        patch("pig_llm.providers.anthropic.anthropic.Anthropic", return_value=client),
        patch("pig_llm.providers.anthropic.anthropic.AsyncAnthropic", return_value=client),
    ):
        return LLM(
            provider="anthropic",
            api_key="test",
            model="claude-opus-4-8",
            enable_web_search=enable_web_search,
            **extra,
        )


def test_anthropic_enable_web_search_injects_native_tool():
    create = Mock(return_value=_anthropic_response())
    llm = _anthropic_llm(create, enable_web_search=True)

    llm.chat(
        [Message(role="user", content="what's new today?")],
        model="claude-opus-4-8",
        tools=[{"type": "function", "function": {"name": "foo", "parameters": {}}}],
    )

    sent_tools = create.call_args.kwargs["tools"]
    # Native server tool is present, alongside the converted function tool.
    assert NATIVE in sent_tools
    assert any(t.get("name") == "foo" for t in sent_tools)
    # Control flags must never reach the SDK as raw kwargs.
    assert "enable_web_search" not in create.call_args.kwargs
    assert "web_search_max_uses" not in create.call_args.kwargs


def test_anthropic_web_search_custom_max_uses():
    create = Mock(return_value=_anthropic_response())
    llm = _anthropic_llm(create, enable_web_search=True, web_search_max_uses=3)

    llm.chat([Message(role="user", content="hi")], model="claude-opus-4-8")

    sent_tools = create.call_args.kwargs["tools"]
    assert {"type": "web_search_20250305", "name": "web_search", "max_uses": 3} in sent_tools


def test_anthropic_web_search_disabled_no_native_tool():
    create = Mock(return_value=_anthropic_response())
    llm = _anthropic_llm(create, enable_web_search=False)

    llm.chat([Message(role="user", content="hi")], model="claude-opus-4-8")

    # No tools at all → the SDK call omits `tools` entirely.
    assert "tools" not in create.call_args.kwargs


def test_non_anthropic_provider_never_receives_web_search():
    """A non-Anthropic provider must not receive the native tool or control flags."""
    pytest.importorskip("openai")
    create = Mock(return_value=_openai_response())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with (
        patch("pig_llm.providers.openai.openai.OpenAI", return_value=client),
        patch("pig_llm.providers.openai.openai.AsyncOpenAI", return_value=client),
    ):
        llm = LLM(provider="openai", api_key="test", model="gpt-4o-mini", enable_web_search=True)

    llm.chat([Message(role="user", content="hi")], model="gpt-4o-mini")

    sent = create.call_args.kwargs
    assert "enable_web_search" not in sent
    assert "web_search_max_uses" not in sent
    # No native Anthropic tool leaked into the OpenAI call.
    assert NATIVE not in (sent.get("tools") or [])


def test_server_tool_result_blocks_are_not_extracted_as_tool_calls():
    """Server-executed web search returns server_tool_use/web_search_tool_result
    blocks (not tool_use); these must never surface as locally-dispatched calls."""
    pytest.importorskip("anthropic")
    from pig_llm.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    content = [
        SimpleNamespace(type="server_tool_use", id="srv_1", name="web_search"),
        SimpleNamespace(type="web_search_tool_result", tool_use_id="srv_1"),
        SimpleNamespace(type="text", text="Here is what I found."),
    ]
    assert provider._extract_tool_calls(content) is None
