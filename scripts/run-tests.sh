#!/usr/bin/env bash
# Run root and package suites independently while accumulating coverage.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

if [[ -z "${PYTEST:-}" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/pytest" ]]; then
    PYTEST="$REPO_ROOT/.venv/bin/pytest"
  else
    PYTEST="pytest"
  fi
fi

if [[ -z "${COVERAGE:-}" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/coverage" ]]; then
    COVERAGE="$REPO_ROOT/.venv/bin/coverage"
  else
    COVERAGE="coverage"
  fi
fi

echo "Running root integration tests..."
"$PYTEST" tests/ -q -o addopts='' --strict-markers --tb=short \
  --cov=packages --cov-report=

for pkg in packages/*/; do
  if [[ -d "$pkg/tests" ]]; then
    echo "Running $pkg tests..."
    "$PYTEST" "$pkg/tests" -q -o addopts='' --strict-markers --tb=short \
      --cov=packages --cov-append --cov-report=
  fi
done

"$COVERAGE" xml
"$COVERAGE" html

echo "All test suites passed."
echo "Coverage reports: $REPO_ROOT/coverage.xml and $REPO_ROOT/htmlcov/index.html"
