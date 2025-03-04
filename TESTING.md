# Playwright Tests

uv sync --group playwright
uv run playwright install-deps
uv run playwright install chromium
pytest -m playwright
