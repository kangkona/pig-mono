"""Contracts for the dependency-light base install and provider extras."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pig_llm import Config, providers
from pig_llm._extras import PROVIDER_EXTRAS, provider_sdk_is_available
from pig_llm.runtime import create_default_runtime


def test_provider_runtime_exports_and_extra_guidance_stay_in_sync() -> None:
    exported_provider_ids = {provider_id for _, provider_id in providers._PROVIDER_EXPORTS.values()}
    runtime_provider_ids = set(create_default_runtime()._providers)

    assert runtime_provider_ids == set(PROVIDER_EXTRAS) == exported_provider_ids


def test_namespace_parent_absence_counts_as_missing_sdk() -> None:
    missing_parent = ModuleNotFoundError("No module named 'google'", name="google")

    with (
        patch("pig_llm._extras.importlib.util.find_spec", side_effect=missing_parent),
        patch(
            "pig_llm._extras.importlib.metadata.distribution",
            side_effect=importlib.metadata.PackageNotFoundError("google-genai"),
        ),
    ):
        assert provider_sdk_is_available("google") is False


def test_installed_distribution_is_not_misreported_when_module_spec_is_broken() -> None:
    with (
        patch("pig_llm._extras.importlib.util.find_spec", return_value=None),
        patch(
            "pig_llm._extras.importlib.metadata.distribution",
            return_value=SimpleNamespace(),
        ),
    ):
        assert provider_sdk_is_available("openai") is True


def test_sdk_probe_preserves_unrelated_module_failure() -> None:
    internal_error = ModuleNotFoundError("probe implementation failed", name="sniffio")

    with (
        patch("pig_llm._extras.importlib.util.find_spec", side_effect=internal_error),
        pytest.raises(ModuleNotFoundError) as caught,
    ):
        provider_sdk_is_available("google")

    assert caught.value is internal_error


@pytest.mark.parametrize(
    ("provider", "extra"),
    [
        ("anthropic", "anthropic"),
        ("azure", "openai"),
        ("bedrock", "bedrock"),
        ("cerebras", "openai"),
        ("cohere", "cohere"),
        ("deepseek", "openai"),
        ("google", "google"),
        ("groq", "groq"),
        ("mistral", "mistral"),
        ("openai", "openai"),
        ("openrouter", "openai"),
        ("perplexity", "openai"),
        ("together", "openai"),
        ("xai", "openai"),
    ],
)
def test_missing_provider_sdk_names_the_installable_extra(
    provider: str,
    extra: str,
) -> None:
    runtime = create_default_runtime()
    config = Config(provider=provider, api_key="test", model="test")

    with (
        patch("pig_llm.runtime.provider_sdk_is_available", return_value=False),
        pytest.raises(ImportError) as caught,
    ):
        runtime.create_provider(config)

    message = str(caught.value)
    assert provider in message
    assert f"pig-llm[{extra}]" in message


def test_unrelated_module_not_found_is_not_rewritten() -> None:
    runtime = create_default_runtime()
    config = Config(provider="openai", api_key="test", model="test")
    missing = ModuleNotFoundError("implementation dependency missing", name="sniffio")

    with (
        patch("pig_llm.runtime.provider_sdk_is_available", return_value=True),
        patch("pig_llm.runtime.importlib.import_module", side_effect=missing),
        pytest.raises(ModuleNotFoundError) as caught,
    ):
        runtime.create_provider(config)

    assert caught.value is missing


def test_provider_constructor_import_error_is_not_rewritten() -> None:
    runtime = create_default_runtime()
    config = Config(provider="openai", api_key="test", model="test")

    class BrokenProvider:
        def __init__(self, _config: Config) -> None:
            raise ImportError("provider implementation bug")

    provider_module = SimpleNamespace(OpenAIProvider=BrokenProvider)
    with (
        patch("pig_llm.runtime.provider_sdk_is_available", return_value=True),
        patch("pig_llm.runtime.importlib.import_module", return_value=provider_module),
        pytest.raises(ImportError, match="provider implementation bug") as caught,
    ):
        runtime.create_provider(config)

    assert "pig-llm[openai]" not in str(caught.value)


def test_provider_package_does_not_rewrite_internal_import_error() -> None:
    internal_error = ImportError("provider module bug")

    with (
        patch("pig_llm.providers.provider_sdk_is_available", return_value=True),
        patch("pig_llm.providers.importlib.import_module", side_effect=internal_error),
        pytest.raises(ImportError) as caught,
    ):
        providers.__getattr__("OpenAIProvider")

    assert caught.value is internal_error


def test_provider_package_names_extra_for_expected_missing_sdk() -> None:
    with (
        patch("pig_llm.providers.provider_sdk_is_available", return_value=False),
        pytest.raises(ImportError, match=r"pig-llm\[openai\]"),
    ):
        providers.__getattr__("OpenAIProvider")


def test_installed_but_broken_sdk_is_not_reported_as_missing() -> None:
    runtime = create_default_runtime()
    config = Config(provider="openai", api_key="test", model="test")
    loader_error = ModuleNotFoundError(
        "installed openai failed during initialization",
        name="openai",
    )

    with (
        patch("pig_llm.runtime.provider_sdk_is_available", return_value=True),
        patch("pig_llm.runtime.importlib.import_module", side_effect=loader_error),
        pytest.raises(ModuleNotFoundError) as caught,
    ):
        runtime.create_provider(config)

    assert caught.value is loader_error
    assert "pig-llm[openai]" not in str(caught.value)


def test_importing_pig_llm_does_not_import_provider_sdks() -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(source), environment.get("PYTHONPATH", "")) if item
    )
    code = """
import sys
import pig_llm

sdk_modules = (
    "anthropic",
    "boto3",
    "cohere",
    "google.genai",
    "groq",
    "mistralai",
    "openai",
)
loaded = [name for name in sdk_modules if name in sys.modules]
if loaded:
    raise SystemExit(f"provider SDKs imported by base package: {loaded}")
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
