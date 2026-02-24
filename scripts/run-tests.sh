#!/bin/bash
# Run all tests with coverage

set -e

echo "==================================="
echo "Running pig-mono Test Suite"
echo "==================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "\n${BLUE}1. Running unit tests...${NC}"
pytest tests/ packages/*/tests -v --cov=packages --cov-report=term-missing

echo -e "\n${BLUE}2. Generating coverage report...${NC}"
pytest --cov=packages --cov-report=html --cov-report=xml

echo -e "\n${GREEN}✓ Tests complete!${NC}"
echo -e "Coverage report: ${REPO_ROOT}/htmlcov/index.html"
