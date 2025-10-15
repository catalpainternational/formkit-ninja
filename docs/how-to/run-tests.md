# How to Run Tests

Quick guide to set up and run the FormKit Ninja test suite.

---

## Prerequisites

- Python 3.11+
- PostgreSQL database
- `uv` or `pip` installed

---

## Step 1: Clone the Repository

```bash
gh repo clone catalpainternational/formkit-ninja
cd formkit-ninja
```

---

## Step 2: Install Dependencies

=== "uv (Recommended)"
    ```bash
    uv sync
    ```

=== "pip"
    ```bash
    pip install -e ".[dev]"
    ```

**Expected output:**
```
Resolved 45 packages in 1.2s
Installed 45 packages in 234ms
```

---

## Step 3: Start PostgreSQL

The test suite requires a running PostgreSQL database.

=== "Docker"
    ```bash
    docker run -d \
      --name formkit-test-db \
      -p 5432:5432 \
      -e POSTGRES_HOST_AUTH_METHOD=trust \
      postgres:17
    ```

=== "Podman"
    ```bash
    podman run -d \
      --name formkit-test-db \
      -p 5432:5432 \
      -e POSTGRES_HOST_AUTH_METHOD=trust \
      postgres:17
    ```

=== "Local PostgreSQL"
    Ensure your PostgreSQL server is running and accessible on port 5432.

**Verify it's running:**
```bash
psql -h localhost -U postgres -c "SELECT version();"
```

---

## Step 4: Run the Tests

Run the full test suite with pytest:

```bash
uv run pytest
```

**Expected output:**
```
============================= test session starts ==============================
platform linux -- Python 3.11.7, pytest-8.0.0, pluggy-1.4.0
rootdir: /path/to/formkit-ninja
plugins: django-4.9.0, cov-6.0.0
collected 89 items

tests/test_admin.py ................                                     [ 18%]
tests/test_formkit_in.py ........                                        [ 27%]
tests/test_json_table.py .......                                         [ 35%]
tests/test_models.py .....................                               [ 59%]
tests/test_parser.py ..........                                          [ 71%]
tests/test_schema.py ........................                            [100%]

============================== 89 passed in 12.34s ==============================
```

---

## Step 5: Run with Coverage

To see test coverage:

```bash
uv run pytest --cov=formkit_ninja --cov-report=html
```

**View the coverage report:**
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## Running Specific Tests

### Run a Single Test File

```bash
uv run pytest tests/test_admin.py
```

### Run a Specific Test

```bash
uv run pytest tests/test_admin.py::test_json_field_save
```

### Run Tests Matching a Pattern

```bash
uv run pytest -k "admin"
```

---

## Playwright Tests (Optional)

FormKit Ninja includes Playwright tests for browser automation.

### Install Playwright

```bash
# Create shared volume (once)
docker volume create ms-playwright

# Install Playwright in dev container
playwright install chromium
```

### Run Playwright Tests

```bash
uv run pytest tests/test_pw.py
```

!!! warning "Headless Mode"
    Playwright tests run in headless mode by default. For debugging, use:
    ```bash
    uv run pytest tests/test_pw.py --headed
    ```

---

## Troubleshooting

### Database Connection Failed

**Problem:**
```
psycopg2.OperationalError: connection to server at "localhost", port 5432 failed
```

**Solution:**
- Ensure PostgreSQL is running: `docker ps` or `podman ps`
- Check port 5432 is not in use: `lsof -i :5432`
- Restart the container

### Tests Fail with Migration Errors

**Problem:**
```
django.db.utils.ProgrammingError: relation "formkit_ninja_formkitschema" does not exist
```

**Solution:**
Run migrations first:
```bash
uv run python manage.py migrate
```

### Import Errors

**Problem:**
```
ImportError: No module named 'formkit_ninja'
```

**Solution:**
Install in editable mode:
```bash
uv pip install -e .
```

---

## Environment Variables

Control test behavior with environment variables:

```bash
# Use custom PostgreSQL port
POSTGRES_PORT=5433 uv run pytest

# Use custom password
POSTGRES_PASSWORD=mypassword uv run pytest

# Use custom host
POSTGRES_HOST=db.example.com uv run pytest
```

---

## CI/CD Integration

The test suite runs in GitHub Actions. See `.github/workflows/` for configuration.

**Next**: [Manage Options →](manage-options.md)

