"""Dependency topology contracts for the public packages."""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
tomllib: ModuleType = importlib.import_module("tomllib" if sys.version_info >= (3, 11) else "tomli")
PROVIDER_REQUIREMENTS = {
    "anthropic": "anthropic>=0.18.0",
    "bedrock": "boto3>=1.34.0",
    "cohere": "cohere>=7.0.8",
    "google": "google-genai>=0.1.0",
    "groq": "groq>=0.4.0",
    "mistral": "mistralai>=0.1.0",
    "openai": "openai>=1.12.0",
}


def _project(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return cast(dict[str, Any], tomllib.load(handle)["project"])


def _requirement_name(requirement: str) -> str:
    match = re.match(r"^[A-Za-z0-9_.-]+", requirement)
    assert match is not None
    return re.sub(r"[-_.]+", "-", match.group()).lower()


def test_pig_llm_base_install_contains_only_runtime_core() -> None:
    project = _project(REPO_ROOT / "packages" / "pig-llm" / "pyproject.toml")

    assert project["dependencies"] == ["pydantic>=2.6.0"]


def test_pig_llm_provider_sdks_are_explicit_optional_extras() -> None:
    project = _project(REPO_ROOT / "packages" / "pig-llm" / "pyproject.toml")
    optional = project["optional-dependencies"]

    for extra, requirement in PROVIDER_REQUIREMENTS.items():
        assert optional[extra] == [requirement]
    assert set(optional["all"]) == set(PROVIDER_REQUIREMENTS.values())
    assert set(PROVIDER_REQUIREMENTS.values()).issubset(optional["dev"])


def test_default_downstream_packages_do_not_force_provider_extras() -> None:
    for package in ("pig-agent-core", "pig-coding-agent", "pig-messenger", "pig-web-ui"):
        project = _project(REPO_ROOT / "packages" / package / "pyproject.toml")
        pig_llm_requirements = [
            requirement
            for requirement in project["dependencies"]
            if _requirement_name(requirement) == "pig-llm"
        ]

        assert pig_llm_requirements == ["pig-llm>=0.2.0"]


def test_workspace_development_environment_requests_all_provider_sdks() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        workspace = tomllib.load(handle)

    assert "pig-llm[all]" in workspace["dependency-groups"]["dev"]
