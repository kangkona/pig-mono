# Testing guide

pig-mono keeps root integration tests and package-local tests separate because
several packages contain same-named support modules such as `conftest.py`. CI runs
the root suite first and then each package suite in isolation.

## Install the development workspace

```bash
uv sync --all-packages
```

The equivalent pip setup is defined in `.github/workflows/ci.yml`. Use the `uv`
workspace and its root `uv.lock` for local development unless reproducing a CI
environment. Package-local lockfile copies are intentionally not maintained.

## Run the verification suite

```bash
./scripts/lint.sh
./scripts/typecheck.sh
./scripts/run-tests.sh
```

`run-tests.sh` prefers the repository `.venv`, runs the root tests, then every
package test directory, while appending coverage into one report. It writes
terminal output, `coverage.xml`, and an HTML report under `htmlcov/`.

To run the same test shape manually:

```bash
pytest tests/ -q -o addopts='' --strict-markers --tb=short \
  --cov=packages --cov-report=

for pkg in packages/*/; do
  if [ -d "$pkg/tests" ]; then
    pytest "$pkg/tests" -q -o addopts='' --strict-markers --tb=short \
      --cov=packages --cov-append --cov-report=
  fi
done

coverage xml
coverage html
```

## Focused tests

```bash
# One package
pytest packages/pig-agent-core/tests/ -v

# One file
pytest packages/pig-coding-agent/tests/test_turn_lifecycle.py -v

# One test
pytest packages/pig-llm/tests/test_runtime.py::test_llm_profile_clone_rebuilds_provider_with_selected_key -v
```

## Release integrity tests

The release verifier checks all six public packages against one tag:

```bash
python scripts/verify_release.py --tag v0.2.0
```

It fails when any of these facts disagree:

- the tag version;
- the workspace and package manifest versions;
- the package's import-time `__version__`;
- a local package dependency floor;
- the root changelog release heading; or
- the expected public package set.

After Trusted Publishing, the release workflow runs the same verifier with
`--published-dist`. That mode requires exactly one wheel and one source archive
per package and compares their SHA-256 digests with PyPI before a GitHub Release is
created.

## CI matrix

`.github/workflows/ci.yml` runs on Linux, macOS, and Windows with Python 3.10,
3.11, and 3.12. Each test job runs:

1. package installation in dependency order;
2. Ruff lint and format checks;
3. strict mypy checks for production, tests, and examples; and
4. root and package-local pytest suites.

The build job creates every distribution and requires `twine check` to pass. The
docs job verifies that every public package includes a README.

## Writing tests

- Put cross-package contracts in `tests/`.
- Put package behavior next to the owning package under `packages/<name>/tests/`.
- Prefer deterministic fake providers and tools over live credentials.
- Assert structured outcomes, permission denials, events, and durable state rather
  than only checking rendered text.
- For state transitions, cover rejection and rollback paths as well as success.
- Keep external-provider tests opt-in and never make a normal test run depend on a
  developer's credentials.

Coverage output is evidence for the commit that produced it, not a permanent
project fact. This guide intentionally does not publish a static test count or
coverage percentage.
