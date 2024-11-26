FROM mcr.microsoft.com/devcontainers/python:1-3-bookworm AS builder

ENV PYTHONUNBUFFERED 1

RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    clang python3-dev libpq-dev \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
ENV PATH="$UV_PROJECT_ENVIRONMENT/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

# For requirements compilation
FROM builder AS sync
WORKDIR /app
ADD . /app
RUN --mount=type=cache,sharing=locked,target=/root/.cache/ \
    uv sync --no-install-workspace 

FROM builder AS final
COPY --from=sync --chown=vscode:vscode /opt/venv /opt/venv
