#!/bin/bash
# Run linting and formatting checks

set -e

echo "Running linting and formatting..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

# Run ruff
echo "→ Running ruff..."
ruff check packages/

echo "→ Running ruff format check..."
ruff format --check packages/

# Run mypy
echo "→ Running mypy..."
./scripts/typecheck.sh

echo "✓ All checks passed!"
