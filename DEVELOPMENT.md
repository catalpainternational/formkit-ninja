# Development Setup

This guide describes how to recreate the development environment with real data from Partisipa.

## Prerequisites

- Python 3.10+
- `uv` (for package management)
- Docker or Podman (for the database)

## Database Setup

Start a local PostgreSQL instance:

```bash
# Using Docker
docker run -d --name formkit-postgres -p 5433:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:14-alpine

# OR Using Podman
podman run -d --name formkit-postgres -p 5433:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:14-alpine
```

## Installation

Install dependencies:

```bash
uv sync
```

## Migrations

Apply database migrations:

```bash
uv run python manage.py migrate
uv run python manage.py pgtrigger install
```

## Loading Partisipa Fixtures

We have exported real data from the Partisipa environment into compressed fixtures located in `formkit_ninja/fixtures/`.

To load this data, you need to temporarily disable protection triggers.

1. **Disable Triggers:**

```bash
uv run python manage.py pgtrigger disable formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates
uv run python manage.py pgtrigger disable formkit_ninja.FormKitSchemaNode:protect_node_updates
```

2. **Load Data:**

```bash
uv run python manage.py loaddata formkit_ninja/fixtures/partisipa_contenttypes.json.gz formkit_ninja/fixtures/partisipa_formkit_data.json.gz
```

3. **Re-enable Triggers:**

```bash
uv run python manage.py pgtrigger enable formkit_ninja.FormKitSchemaNode:protect_node_deletes_and_updates
uv run python manage.py pgtrigger enable formkit_ninja.FormKitSchemaNode:protect_node_updates
```

## Verification

You can verify the data load by checking the object counts:

```bash
uv run python manage.py shell -c "from formkit_ninja.models import FormKitSchemaNode; print(f'Nodes: {FormKitSchemaNode.objects.count()}')"
```

Expected count: ~647 nodes.

## Architecture Extension Points

- `SchemaWalker` in `formkit_ninja/parser/schema_walker.py` centralizes schema traversal and NodePath collection.
- `GenerationPipeline` in `formkit_ninja/parser/generation_pipeline.py` composes generation steps without expanding `CodeGenerator.generate`.
- `SchemaImportService` in `formkit_ninja/services/schema_import.py` owns schema and option import logic used by models and commands.
- `FormKitNodeFactory` in `formkit_ninja/parser/node_factory.py` standardizes parsing from dict/JSON for node creation.
- `NodeRegistry` in `formkit_ninja/parser/node_registry.py` maps node type identifiers (e.g., "$formkit" values) to Pydantic model classes. Use `default_registry` for common nodes, or create a custom registry for extensions. The factory uses the registry when parsing, falling back to `FormKitNode.parse_obj` for backward compatibility.
- `Notifier` in `formkit_ninja/notifications.py` abstracts optional integrations (Sentry vs no-op).

### Node Registry Usage

The `NodeRegistry` provides a centralized way to map FormKit node types to their Pydantic model classes. This enables:

- **Extensibility**: Register custom node types without modifying core parsing logic
- **Type Safety**: Explicit mapping between node identifiers and classes
- **Centralized Parsing**: `FormKitNodeFactory` uses the registry as the primary parsing entry point

**Example:**
```python
from formkit_ninja.parser.node_registry import NodeRegistry, default_registry
from formkit_ninja.formkit_schema import TextNode

# Use default registry (pre-populated with common nodes)
node_class = default_registry.get_formkit_node_class("text")
assert node_class == TextNode

# Or create a custom registry for extensions
custom_registry = NodeRegistry()
custom_registry.register_formkit_node("custom_type", CustomNodeClass)
```

**Parsing Entry Point:**
Always use `FormKitNodeFactory.from_dict()` or `FormKitNodeFactory.from_json()` for parsing node data. The factory will:
1. Check the registry for registered node types
2. Fall back to `FormKitNode.parse_obj()` for backward compatibility
3. Raise `ValueError` if parsing fails

## CI Tooling Notes

- Prefer `uv run ruff check .`, `uv run ruff format .`, `uv run mypy .`, and `uv run pytest` for local checks.
- Pre-commit runs `uv run mypy formkit_ninja` (source-only). Full-tree mypy includes test fixtures that currently report errors.
