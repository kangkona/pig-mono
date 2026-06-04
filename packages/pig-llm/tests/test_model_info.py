"""Tests for the generated model registry lookup."""

from pig_llm import get_model_info


def test_lookup_exact_id():
    info = get_model_info("gpt-4o-mini")
    assert info is not None
    assert info["context_window"] == 128000
    assert info["input_cost"] == 0.15
    assert info["output_cost"] == 0.6


def test_lookup_bare_from_vendor_prefixed_id():
    # OpenRouter-style "vendor/model" resolves via the bare name.
    info = get_model_info("google/gemini-3.5-flash")
    assert info is not None
    assert info["context_window"] == 1048576


def test_unknown_model_returns_none():
    assert get_model_info("totally-made-up-model-zzz") is None
    assert get_model_info("") is None
    assert get_model_info(None) is None
