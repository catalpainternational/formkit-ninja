FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

ENV PYTHONUNBUFFERED=1

ENV VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
ENV PATH="/opt/venv/bin:$PATH"

# For requirements compilation (Prod image)
# Copy app files and run `uv sync`
WORKDIR /app
COPY pyproject.toml uv.lock /app/
COPY --from=ghcr.io/astral-sh/uv:0.6.9 /uv /usr/local/bin/uv
RUN --mount=type=cache,sharing=locked,target=/root/.cache/ \
    uv sync --no-install-workspace

# COPY src/formkit_ninja /app/formkit_ninja
# COPY testproject /app/testproject
# COPY manage.py /app/
