#!/usr/bin/env bash
# Check production sources strictly and test/example bodies package by package.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

if [[ -z "${MYPY:-}" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/mypy" ]]; then
    MYPY="$REPO_ROOT/.venv/bin/mypy"
  else
    MYPY="mypy"
  fi
fi

echo "→ Strict production source check..."
"$MYPY"

echo "→ Checking root integration tests..."
"$MYPY" tests --config-file "$REPO_ROOT/pyproject.toml"

check_package_support_code() {
  local package="$1"
  shift

  echo "→ Checking $package tests and examples..."
  (
    cd "$REPO_ROOT/packages/$package"
    "$MYPY" src tests "$@" \
      --config-file "$REPO_ROOT/pyproject.toml"
  )
}

check_package_support_code pig-agent-core examples
check_package_support_code pig-coding-agent
check_package_support_code pig-llm examples
check_package_support_code pig-messenger examples
check_package_support_code pig-tui
check_package_support_code pig-web-ui

echo "✓ Repository type checks passed"
