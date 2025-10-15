#!/bin/bash
# Build FormKit Ninja documentation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "📚 Building FormKit Ninja Documentation"
echo "========================================"

cd "$PROJECT_ROOT"

# Use docs/pyproject.toml for dependencies
echo "📦 Using dependencies from docs/pyproject.toml"
echo ""

# Build from project root, using docs environment
uv run --directory docs mkdocs build \
    --config-file ../mkdocs.yml \
    --site-dir ../site

echo ""
echo "✅ Documentation built successfully!"
echo "📁 Output: $PROJECT_ROOT/site/"
