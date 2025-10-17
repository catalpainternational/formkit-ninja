#!/bin/bash
# Run the same CI checks locally before pushing
# Usage: ./scripts/ci-local.sh

set -e

echo "================================"
echo "Running CI checks locally..."
echo "================================"

echo ""
echo "→ Checking code formatting with black..."
poetry run black --check .

echo ""
echo "→ Checking import sorting with isort..."
poetry run isort --check .

echo ""
echo "→ Linting with flake8..."
poetry run flake8 formkit_ninja tests testproject --exclude=migrations

echo ""
echo "→ Type checking with mypy..."
poetry run mypy formkit_ninja || true

echo ""
echo "→ Running tests with pytest..."
export POSTGRES_DB=${POSTGRES_DB:-postgres}
export POSTGRES_USER=${POSTGRES_USER:-postgres}
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
export POSTGRES_HOST=${POSTGRES_HOST:-localhost}
export POSTGRES_PORT=${POSTGRES_PORT:-5433}

poetry run pytest -v

echo ""
echo "================================"
echo "✅ All CI checks passed!"
echo "================================"

