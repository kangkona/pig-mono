"""Per-compat thinking/reasoning-level matrix.

apply_thinking_level is the most branch-heavy part of the compat layer: each
provider family expresses "how hard to think" differently (reasoning_effort,
nested reasoning, thinking dict, enable_thinking flag, ...). These tests pin the
emitted parameter shape per family and that "off" / unknown levels strip cleanly
— mirroring pi-mono's per-quirk thinking tests.
"""

from __future__ import annotations

import pytest
from pig_llm.compat import (
    DEEPSEEK_COMPAT,
    GROQ_COMPAT,
    OPENAI_COMPAT,
    OPENROUTER_COMPAT,
    QWEN_COMPAT,
    ZAI_COMPAT,
    apply_thinking_level,
)

# All "thinking" keys a request might carry; tests assert exactly one family-
# specific key survives and the others are stripped.
_ALL_THINKING_KEYS = {"thinking", "reasoning", "reasoning_effort", "enable_thinking"}


def _apply(compat, level, model):
    return apply_thinking_level({"thinking_level": level, "model": model}, compat)


def test_openai_uses_reasoning_effort():
    out = _apply(OPENAI_COMPAT, "high", "gpt-4o")
    assert out["reasoning_effort"] == "high"
    assert "thinking" not in out and "reasoning" not in out


def test_groq_uses_reasoning_effort():
    out = _apply(GROQ_COMPAT, "medium", "llama-3.3-70b-versatile")
    assert out["reasoning_effort"] == "medium"
    assert "thinking" not in out and "reasoning" not in out


def test_openrouter_uses_nested_reasoning():
    out = _apply(OPENROUTER_COMPAT, "high", "openai/gpt-4o")
    assert out["reasoning"] == {"effort": "high"}
    assert "thinking" not in out and "reasoning_effort" not in out


def test_deepseek_uses_thinking_type_dict():
    on = _apply(DEEPSEEK_COMPAT, "high", "deepseek-chat")
    assert on["thinking"] == {"type": "enabled"}
    off = _apply(DEEPSEEK_COMPAT, "off", "deepseek-chat")
    assert off["thinking"] == {"type": "disabled"}


def test_qwen_and_zai_use_enable_thinking_flag():
    assert _apply(QWEN_COMPAT, "high", "qwen")["enable_thinking"] is True
    assert _apply(QWEN_COMPAT, "off", "qwen")["enable_thinking"] is False
    assert _apply(ZAI_COMPAT, "high", "glm")["enable_thinking"] is True
    assert _apply(ZAI_COMPAT, "off", "glm")["enable_thinking"] is False


@pytest.mark.parametrize(
    "compat,model",
    [
        (OPENAI_COMPAT, "gpt-4o"),
        (GROQ_COMPAT, "llama-3.3-70b-versatile"),
        (OPENROUTER_COMPAT, "openai/gpt-4o"),
    ],
    ids=["openai", "groq", "openrouter"],
)
def test_off_strips_reasoning_to_explicit_disable_or_none(compat, model):
    """'off' must not leave a stale enabled-reasoning payload around."""
    out = _apply(compat, "off", model)
    # Either a normalized 'none'/disable value or fully stripped — never an
    # 'enabled'/'high' reasoning payload.
    if compat is OPENAI_COMPAT or compat is GROQ_COMPAT:
        assert out.get("reasoning_effort") == "none"
    elif compat is OPENROUTER_COMPAT:
        assert out.get("reasoning") == {"effort": "none"}


@pytest.mark.parametrize(
    "compat,model",
    [
        (OPENAI_COMPAT, "gpt-4o"),
        (GROQ_COMPAT, "llama-3.3-70b-versatile"),
        (OPENROUTER_COMPAT, "openai/gpt-4o"),
        (DEEPSEEK_COMPAT, "deepseek-chat"),
        (QWEN_COMPAT, "qwen"),
        (ZAI_COMPAT, "glm"),
    ],
    ids=["openai", "groq", "openrouter", "deepseek", "qwen", "zai"],
)
def test_unknown_level_strips_all_thinking_keys(compat, model):
    """An unmapped thinking level removes every thinking-family key."""
    out = apply_thinking_level(
        {"thinking_level": "bogus-level", "model": model, "thinking": {"x": 1}}, compat
    )
    assert not (_ALL_THINKING_KEYS & set(out)), f"leftover thinking keys: {set(out)}"


@pytest.mark.parametrize(
    "compat,model",
    [
        (OPENAI_COMPAT, "gpt-4o"),
        (DEEPSEEK_COMPAT, "deepseek-chat"),
        (QWEN_COMPAT, "qwen"),
    ],
    ids=["openai", "deepseek", "qwen"],
)
def test_no_thinking_level_is_passthrough(compat, model):
    """Without a thinking_level, the request is untouched."""
    out = apply_thinking_level({"model": model, "temperature": 0.5}, compat)
    assert out == {"model": model, "temperature": 0.5}


@pytest.mark.parametrize(
    "compat,model,key",
    [
        (OPENAI_COMPAT, "gpt-4o", "reasoning_effort"),
        (GROQ_COMPAT, "llama-3.3-70b-versatile", "reasoning_effort"),
        (OPENROUTER_COMPAT, "openai/gpt-4o", "reasoning"),
        (DEEPSEEK_COMPAT, "deepseek-chat", "thinking"),
        (QWEN_COMPAT, "qwen", "enable_thinking"),
        (ZAI_COMPAT, "glm", "enable_thinking"),
    ],
    ids=["openai", "groq", "openrouter", "deepseek", "qwen", "zai"],
)
def test_each_family_emits_exactly_one_thinking_key(compat, model, key):
    """Each family sets its own key and strips the others (no cross-leak)."""
    out = _apply(compat, "high", model)
    present = _ALL_THINKING_KEYS & set(out)
    assert present == {key}, f"expected only {key}, got {present}"
