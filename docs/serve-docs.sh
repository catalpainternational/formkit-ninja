#!/bin/bash
# Serve FormKit Ninja documentation with live reload

set -e

PORT="${1:-8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "📚 FormKit Ninja Documentation Server"
echo "======================================"

cd "$PROJECT_ROOT"

# Use docs/pyproject.toml for dependencies
echo "🚀 Starting server on http://localhost:$PORT"
echo "📦 Using dependencies from docs/pyproject.toml"
echo ""

# Serve from project root, using docs environment
uv run --directory docs mkdocs serve \
    --config-file ../mkdocs.yml \
    --dev-addr "0.0.0.0:$PORT"

