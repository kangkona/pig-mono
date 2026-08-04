#!/bin/bash
# Run linting and formatting checks

set -e

echo "Running linting and formatting..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

if [[ -z "${RUFF:-}" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/ruff" ]]; then
    RUFF="$REPO_ROOT/.venv/bin/ruff"
  else
    RUFF="ruff"
  fi
fi

# Run ruff
echo "→ Running ruff..."
"$RUFF" check packages/ tests/ scripts/verify_release.py scripts/verify_minimal_pig_llm.py

echo "→ Running ruff format check..."
"$RUFF" format --check packages/ tests/ scripts/verify_release.py scripts/verify_minimal_pig_llm.py

# Run mypy
echo "→ Running mypy..."
./scripts/typecheck.sh

echo "✓ All checks passed!"
