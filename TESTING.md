# Testing

## Database Setup

Tests require PostgreSQL 17. Start a test container:

```bash
podman run -d --name formkit-test-db -p 5433:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=postgres \
  postgres:17
```

Run tests with:
```bash
POSTGRES_PORT=5433 POSTGRES_PASSWORD=postgres uv run pytest
```

## Playwright Tests

uv sync --group playwright
uv run playwright install-deps
uv run playwright install chromium
pytest -m playwright
