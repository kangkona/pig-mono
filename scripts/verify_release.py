#!/usr/bin/env python3
"""Verify release metadata and published artifact integrity for pig-mono."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


PACKAGE_NAMES = (
    "pig-agent-core",
    "pig-coding-agent",
    "pig-llm",
    "pig-messenger",
    "pig-tui",
    "pig-web-ui",
)


class ReleaseVerificationError(RuntimeError):
    """Raised when release facts do not agree."""


def _canonicalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _version_from_module(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "__version__":
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise ReleaseVerificationError(f"Missing string __version__ assignment in {path}")


def load_package_metadata(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Load the six public package manifests and their import versions."""
    packages: dict[str, dict[str, Any]] = {}
    package_root = repo_root / "packages"
    for manifest in sorted(package_root.glob("*/pyproject.toml")):
        with manifest.open("rb") as handle:
            project = tomllib.load(handle)["project"]
        name = _canonicalize_name(str(project["name"]))
        module_name = name.replace("-", "_")
        module_init = manifest.parent / "src" / module_name / "__init__.py"
        packages[name] = {
            "version": str(project["version"]),
            "module_version": _version_from_module(module_init),
            "dependencies": tuple(str(item) for item in project.get("dependencies", ())),
            "manifest": manifest,
        }
    return packages


def verify_metadata(repo_root: Path, tag: str) -> dict[str, str]:
    """Verify package, import, dependency, changelog, and tag versions agree."""
    if not tag.startswith("v") or len(tag) == 1:
        raise ReleaseVerificationError(f"Release tag must use v<version>, got {tag!r}")
    tag_version = tag[1:]
    with (repo_root / "pyproject.toml").open("rb") as handle:
        workspace_project = tomllib.load(handle)["project"]
    packages = load_package_metadata(repo_root)
    actual_names = set(packages)
    expected_names = set(PACKAGE_NAMES)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        raise ReleaseVerificationError(
            f"Public package set changed; missing={missing}, unexpected={unexpected}"
        )

    errors: list[str] = []
    workspace_version = str(workspace_project["version"])
    if workspace_version != tag_version:
        errors.append(f"pig-mono: workspace manifest {workspace_version} != tag {tag_version}")
    versions: dict[str, str] = {}
    for name in PACKAGE_NAMES:
        metadata = packages[name]
        version = str(metadata["version"])
        versions[name] = version
        if version != tag_version:
            errors.append(f"{name}: manifest {version} != tag {tag_version}")
        module_version = str(metadata["module_version"])
        if module_version != version:
            errors.append(f"{name}: __version__ {module_version} != manifest {version}")

        for dependency in metadata["dependencies"]:
            match = re.match(r"^([A-Za-z0-9_.-]+)", dependency)
            if match is None:
                continue
            dependency_name = _canonicalize_name(match.group(1))
            if dependency_name not in expected_names:
                continue
            normalized_requirement = dependency.replace(" ", "")
            expected_floor = f">={tag_version}"
            if expected_floor not in normalized_requirement:
                errors.append(
                    f"{name}: local dependency {dependency!r} must include {expected_floor}"
                )

    changelog = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{tag_version}]" not in changelog:
        errors.append(f"CHANGELOG.md has no {tag_version} release heading")

    if errors:
        raise ReleaseVerificationError("\n".join(errors))
    return versions


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_local_artifacts(
    dist_dir: Path, package_versions: Mapping[str, str]
) -> dict[str, dict[str, str]]:
    """Map each package to its expected artifact filenames and SHA-256 digests."""
    result: dict[str, dict[str, str]] = {}
    paths = tuple(path for path in sorted(dist_dir.iterdir()) if path.is_file())
    for name, version in package_versions.items():
        prefix = f"{name.replace('-', '_')}-{version}"
        package_paths = tuple(path for path in paths if path.name.startswith(prefix))
        wheels = [path for path in package_paths if path.suffix == ".whl"]
        sdists = [path for path in package_paths if path.name.endswith(".tar.gz")]
        if len(wheels) != 1 or len(sdists) != 1 or len(package_paths) != 2:
            raise ReleaseVerificationError(
                f"{name}: expected one wheel and one sdist for {version}, "
                f"found {[path.name for path in package_paths]}"
            )
        result[name] = {path.name: _sha256(path) for path in package_paths}
    expected_count = len(package_versions) * 2
    if len(paths) != expected_count:
        raise ReleaseVerificationError(
            f"Expected exactly {expected_count} release artifacts, found {len(paths)}"
        )
    return result


def compare_pypi_payload(expected: Mapping[str, str], payload: Mapping[str, Any]) -> None:
    """Require PyPI to expose exactly the locally built filenames and digests."""
    published = {
        str(item["filename"]): str(item["digests"]["sha256"]) for item in payload.get("urls", ())
    }
    if published != dict(expected):
        missing = sorted(set(expected) - set(published))
        unexpected = sorted(set(published) - set(expected))
        mismatched = sorted(
            name for name in set(expected) & set(published) if expected[name] != published[name]
        )
        raise ReleaseVerificationError(
            "Published artifacts differ from this build: "
            f"missing={missing}, unexpected={unexpected}, digest_mismatch={mismatched}"
        )


def _fetch_json(url: str) -> Mapping[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "pig-mono-release-verifier"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.load(response)


def verify_published_artifacts(
    artifacts: Mapping[str, Mapping[str, str]],
    package_versions: Mapping[str, str],
    *,
    attempts: int,
    retry_delay: float,
    fetch_json: Callable[[str], Mapping[str, Any]] = _fetch_json,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait for PyPI, then verify every published file against the local build."""
    remaining = set(package_versions)
    last_errors: dict[str, str] = {}
    for attempt in range(1, attempts + 1):
        for name in sorted(remaining):
            version = package_versions[name]
            url = f"https://pypi.org/pypi/{name}/{version}/json"
            try:
                payload = fetch_json(url)
                compare_pypi_payload(artifacts[name], payload)
            except (ReleaseVerificationError, urllib.error.URLError, TimeoutError) as error:
                last_errors[name] = str(error)
            else:
                remaining.remove(name)
                last_errors.pop(name, None)
        if not remaining:
            return
        if attempt < attempts:
            sleep(retry_delay)
    details = "; ".join(f"{name}: {last_errors[name]}" for name in sorted(remaining))
    raise ReleaseVerificationError(
        f"PyPI did not expose the verified release after {attempts} attempts: {details}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Release tag, for example v0.2.0")
    parser.add_argument(
        "--published-dist",
        type=Path,
        help="After publishing, compare this artifact directory with PyPI",
    )
    parser.add_argument("--attempts", type=int, default=18)
    parser.add_argument("--retry-delay", type=float, default=10.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    try:
        versions = verify_metadata(repo_root, args.tag)
        print(f"Verified release metadata for {args.tag}: {', '.join(versions)}")
        if args.published_dist is not None:
            artifacts = collect_local_artifacts(args.published_dist, versions)
            verify_published_artifacts(
                artifacts,
                versions,
                attempts=args.attempts,
                retry_delay=args.retry_delay,
            )
            print(f"Verified PyPI artifact digests for {args.tag}")
    except (OSError, ReleaseVerificationError, KeyError, TypeError, ValueError) as error:
        print(f"Release verification failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
