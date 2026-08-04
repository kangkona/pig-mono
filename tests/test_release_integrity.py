"""Tests for release metadata and published artifact verification."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_release_verifier() -> ModuleType:
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "verify_release.py"
    spec = importlib.util.spec_from_file_location("verify_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_release = _load_release_verifier()


def test_release_metadata_matches_v0_2_0() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    versions = verify_release.verify_metadata(repo_root, "v0.2.0")

    assert set(versions.values()) == {"0.2.0"}
    assert set(versions) == set(verify_release.PACKAGE_NAMES)


def test_release_metadata_rejects_a_different_tag() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    with pytest.raises(verify_release.ReleaseVerificationError, match="manifest 0.2.0"):
        verify_release.verify_metadata(repo_root, "v0.2.1")


def test_pypi_payload_requires_exact_filenames_and_digests() -> None:
    expected = {
        "pig_llm-0.2.0-py3-none-any.whl": "wheel-digest",
        "pig_llm-0.2.0.tar.gz": "sdist-digest",
    }
    matching_payload = {
        "urls": [
            {"filename": filename, "digests": {"sha256": digest}}
            for filename, digest in expected.items()
        ]
    }

    verify_release.compare_pypi_payload(expected, matching_payload)

    mismatched_payload = {
        "urls": [
            {
                "filename": filename,
                "digests": {"sha256": "different" if index == 0 else digest},
            }
            for index, (filename, digest) in enumerate(expected.items())
        ]
    }
    with pytest.raises(verify_release.ReleaseVerificationError, match="digest_mismatch"):
        verify_release.compare_pypi_payload(expected, mismatched_payload)
