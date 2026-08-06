"""Provider-to-extra metadata shared by lazy import boundaries."""

from __future__ import annotations

import importlib.metadata
import importlib.util
from typing import Final

PROVIDER_EXTRAS: Final[dict[str, str]] = {
    "anthropic": "anthropic",
    "azure": "openai",
    "bedrock": "bedrock",
    "cerebras": "openai",
    "cohere": "cohere",
    "deepseek": "openai",
    "google": "google",
    "groq": "groq",
    "mistral": "mistral",
    "openai": "openai",
    "openrouter": "openai",
    "perplexity": "openai",
    "together": "openai",
    "xai": "openai",
}

EXTRA_SDK_REQUIREMENTS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "anthropic": (("anthropic", "anthropic"),),
    "bedrock": (("boto3", "boto3"), ("botocore", "botocore")),
    "cohere": (("cohere", "cohere"),),
    "google": (("google.genai", "google-genai"),),
    "groq": (("groq", "groq"),),
    "mistral": (("mistralai", "mistralai"),),
    "openai": (("openai", "openai"),),
}


def _sdk_requirement_is_available(module_name: str, distribution_name: str) -> bool:
    """Check an SDK without mistaking an installed broken distribution for absence."""
    try:
        if importlib.util.find_spec(module_name) is not None:
            return True
    except ModuleNotFoundError as error:
        missing_name = error.name or ""
        if module_name != missing_name and not module_name.startswith(f"{missing_name}."):
            raise

    try:
        importlib.metadata.distribution(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def provider_sdk_is_available(
    provider_id: str,
    *,
    extra: str | None = None,
) -> bool:
    """Return whether every module required by the selected extra is installed."""
    extra_name = extra or PROVIDER_EXTRAS[provider_id]
    return all(
        _sdk_requirement_is_available(module, distribution)
        for module, distribution in EXTRA_SDK_REQUIREMENTS[extra_name]
    )


def missing_provider_dependency(provider_id: str, *, extra: str | None = None) -> ImportError:
    """Build an actionable error for an unavailable provider SDK."""
    extra_name = extra or PROVIDER_EXTRAS[provider_id]
    return ImportError(
        f"Provider {provider_id!r} requires an optional SDK. "
        f"Install it with: pip install 'pig-llm[{extra_name}]'"
    )
