ARG BASE_IMAGE=python:3.13-slim
ARG NO_DEV_OPTION="--no-dev"
# For a development container build,
# set BASE_IMAGE to mcr.microsoft.com/devcontainers/python:1-3-bookworm

FROM ghcr.io/astral-sh/uv:0.5 as uv
FROM ${BASE_IMAGE} AS builder

ENV PYTHONUNBUFFERED=1

RUN --mount=type=cache,sharing=locked,target=/var/cache/apt \
    apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    clang python3-dev libpq-dev \
    && apt-get autoremove -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
ENV PATH="/opt/venv/bin:$PATH"

# For requirements compilation (Prod image)
# Copy app files and run `uv sync`
FROM builder AS sync
WORKDIR /app
COPY pyproject.toml uv.lock /app/
RUN --mount=type=cache,sharing=locked,target=/root/.cache/ \
    --mount=from=uv,source=/uv,target=./uv \
    ./uv sync ${NO_DEV_OPTION} --no-install-workspace

# For a "production" build, the application code is copied into the container
# and the dependencies are installed.
# For this build, remember to set BASE_IMAGE to `python:3.13`
# rather than the Microsoft dev container, and the NO_DEV_OPTION to `--no-dev`.
FROM sync AS final_prod
WORKDIR /app
COPY src/formkit_ninja /app/formkit_ninja
COPY testproject /app/testproject
COPY manage.py /app/


# For a "development" build, application code is a mount and the dev dependencies
# are installed.
# To do this, set `BASE_IMAGE` to `mcr.microsoft.com/devcontainers/python:1-3-bookworm`
# and the `NO_DEV_OPTION` to `--dev`.
FROM sync AS final_dev
# We currently do nothing with the dev image, 
# but you could add additional
# imports / uv sync groups here!