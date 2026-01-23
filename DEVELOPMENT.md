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
