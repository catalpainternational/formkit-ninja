# Formkit-Ninja

A Django-Ninja framework for FormKit schemas and form submissions

## Why

FormKit out of the box has awesome schema support - this lets us integrate FormKit instances as Django models

- Upload / edit / download basic FormKit schemas
- Translated "option" values from the Django admin
- Reorder "options" and schema nodes
- List and Fetch schemas for different form types

## Use

To use, `pip install formkit-ninja` and add the following to settings `INSTALLED_APPS`:

```py
INSTALLED_APPS = [
    ...
    "formkit_ninja",
    "ninja",
    ...
]
```

## Code Generation

formkit-ninja can automatically generate Django models, Pydantic schemas, admin classes, and API endpoints from your FormKit schemas.

### Quick Start

Generate code from all schemas in your database:

```bash
./manage.py generate_code --app-name myapp --output-dir ./myapp/generated
```

Generate code for a specific schema:

```bash
./manage.py generate_code --app-name myapp --output-dir ./myapp/generated --schema-label "My Form"
```

### Generated Files

The code generator creates the following files:

- `models.py` - Django models for groups and repeaters
- `schemas.py` - Django Ninja output schemas
- `schemas_in.py` - Django Ninja input schemas (Pydantic BaseModel)
- `admin.py` - Django admin classes
- `api.py` - Django Ninja API endpoints

### Extensibility

formkit-ninja provides multiple extension points for customizing code generation:

- **Custom Type Converters**: Add support for custom FormKit node types
- **Custom NodePath**: Extend NodePath with project-specific logic
- **Plugin System**: Bundle multiple extensions together
- **Custom Templates**: Override Jinja2 templates for generated code

See the [Code Generation Guide](docs/code_generation.md) for detailed documentation and examples.

## API

Formkit-Ninja provides a REST API for managing FormKit schema nodes. The API requires authentication and specific permissions.

### Authentication

All API endpoints require:
- **Authentication**: User must be logged in (session-based authentication)
- **Permission**: User must have the `formkit_ninja.change_formkitschemanode` permission

Unauthenticated requests receive `401 Unauthorized`. Authenticated users without the required permission receive `403 Forbidden`.

### Endpoints

#### Create or Update Node

**POST** `/api/formkit/create_or_update_node`

Creates a new node or updates an existing one.

**Request Body:**
- `uuid` (optional): UUID of node to update. If omitted, a new node is created.
- `parent_id` (optional): UUID of parent node (must be a group or repeater)
- `$formkit`: FormKit node type (e.g., "text", "group", "repeater")
- Other FormKit node properties (label, name, etc.)

**Response:**
- `200 OK`: Success, returns `NodeReturnType` with node data
- `400 Bad Request`: Invalid input (e.g., invalid parent, deleted node)
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Node with provided UUID does not exist (for updates)
- `500 Internal Server Error`: Server error

**Update Behavior:**
- When `uuid` is provided, the node with that UUID is updated
- If the node doesn't exist, returns `404 Not Found`
- If the node is inactive (deleted), returns `400 Bad Request`
- Parent-child relationships are automatically created/updated when `parent_id` is provided

#### Delete Node

**DELETE** `/api/formkit/delete/{node_id}`

Soft deletes a node (sets `is_active=False`).

**Response:**
- `200 OK`: Success, returns `NodeInactiveType`
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Node does not exist

### Response Formats

All successful responses return consistent data structures:

- **NodeReturnType**: For active nodes
  - `key`: UUID of the node
  - `node`: FormKit node data
  - `last_updated`: Timestamp of last change
  - `protected`: Whether the node is protected from deletion

- **NodeInactiveType**: For deleted nodes
  - `key`: UUID of the node
  - `is_active`: `false`
  - `last_updated`: Timestamp of last change
  - `protected`: Whether the node is protected

- **FormKitErrors**: For error responses
  - `errors`: List of error messages
  - `field_errors`: Dictionary of field-specific errors

### Validation

The API validates:
- **Parent existence**: If `parent_id` is provided, the parent node must exist and be a group or repeater
- **Node existence**: If `uuid` is provided for updates, the node must exist and be active
- **FormKit type**: The `$formkit` field must be a valid FormKit node type

## Test

Pull the repo:

```bash
gh repo clone catalpainternational/formkit-ninja
cd formkit-ninja
uv sync
```

### Database Setup

Tests require PostgreSQL due to the `pgtrigger` dependency. Start a PostgreSQL container before running tests:

```bash
# Using Podman (recommended)
podman run -d --name formkit-postgres -p 5433:5432 -e POSTGRES_HOST_AUTH_METHOD=trust docker.io/library/postgres:14-alpine

# OR using Docker
docker run -d --name formkit-postgres -p 5433:5432 -e POSTGRES_HOST_AUTH_METHOD=trust postgres:14-alpine
```

Then run tests:

```bash
uv run pytest
```

### Playwright

Some tests require playwright. Install it with:

```bash
uv run playwright install
```

**Note:** For full development setup with real data, see [DEVELOPMENT.md](DEVELOPMENT.md).

## Lint

Format and lint code using `ruff`:

```bash
# Check formatting
uv run ruff format --check .

# Check linting
uv run ruff check .
```

## For Contributors

### Prerequisites

- Python 3.10-3.14
- `uv` for package management
- Podman or Docker for PostgreSQL database
- Playwright (for browser-based tests)

### Development Workflow

1. **Set up the project:**
   ```bash
   uv sync
   uv run playwright install
   # Start PostgreSQL (see Database Setup above)
   ```

2. **Run tests:**
   ```bash
   uv run pytest
   ```

3. **Check code quality:**
   ```bash
   uv run ruff format --check .
   uv run ruff check .
   uv run mypy formkit_ninja
   ```

4. **Test Driven Development (TDD):**
   - Write tests *before* implementing features
   - Ensure new code is covered by tests
   - Use `pytest` as the testing framework

5. **Code Style:**
   - Use `ruff` for formatting and linting
   - Follow Python type hints for all function arguments and return values
   - Adhere to SOLID principles

6. **Commit Messages:**
   - Use [Conventional Commits](https://www.conventionalcommits.org/) specification
   - Format: `<type>(<scope>): <subject>`

# Updating 'Protected' Nodes

If a node's been protected you cannot change or delete it. To do so, you'll need to temporarily disable the trigger which is on it.

`./manage.py pytrigger disable protect_node_deletes_and_updates`
Make changes
`./manage.py pgtrigger enable protect_node_deletes_and_updates`

See the documentation for more details: https://django-pgtrigger.readthedocs.io/en/2.3.0/commands.html?highlight=disable