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