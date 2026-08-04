#!/usr/bin/env python3
"""Verify that a base pig-llm install imports without provider SDKs."""

from __future__ import annotations

import importlib.util
import sys

PROVIDER_SDK_MODULES = (
    "anthropic",
    "boto3",
    "cohere",
    "google.genai",
    "groq",
    "mistralai",
    "openai",
)


def _is_installed(module: str) -> bool:
    """Return false when either a module or its namespace parent is absent."""
    try:
        return importlib.util.find_spec(module) is not None
    except ModuleNotFoundError:
        return False


def main() -> None:
    """Reject provider SDKs in the environment or the core import graph."""
    installed = [module for module in PROVIDER_SDK_MODULES if _is_installed(module)]
    if installed:
        raise SystemExit(f"base pig-llm install included provider SDKs: {installed}")

    import pig_llm
    from pig_llm.runtime import create_default_runtime

    imported = [module for module in PROVIDER_SDK_MODULES if module in sys.modules]
    if imported:
        raise SystemExit(f"import pig_llm loaded provider SDKs: {imported}")
    if pig_llm.Config(provider="test").provider != "test":
        raise SystemExit("pig-llm core configuration smoke test failed")

    config = pig_llm.Config(provider="openai", api_key="test", model="test")
    try:
        create_default_runtime().create_provider(config)
    except ImportError as error:
        expected = "pip install 'pig-llm[openai]'"
        if expected not in str(error):
            raise SystemExit(f"missing SDK guidance did not name the extra: {error}") from error
    else:
        raise SystemExit("minimal install unexpectedly created an OpenAI provider")


if __name__ == "__main__":
    main()
