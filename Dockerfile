# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
#
# 1. web:     build the web app with Node into src/senseai_studio/static.
# 2. builder: resolve Python deps with uv into /opt/venv.
# 3. app:     slim runtime; uvicorn on $PORT (default 8200).
# Mount a profiles checkout at /senseai/profiles (SENSEAI_STACK_DIR=/senseai) and, for runs,
# a stack with senseai-bench (SENSEAI_BENCH_CMD, SENSEAI_BENCH_PYTHON). Without bench, every
# screen but Run works and Run says why it cannot.

ARG NODE_IMAGE=node:22-slim
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${NODE_IMAGE} AS web
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv
RUN pip install --no-cache-dir uv==0.8.22
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE NOTICE ./
COPY src ./src
COPY --from=web /app/src/senseai_studio/static ./src/senseai_studio/static
RUN uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS app
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8200 \
    SENSEAI_STACK_DIR=/senseai \
    STUDIO_CONTENT=/app/content \
    STUDIO_DATA=/data
COPY --from=builder /opt/venv /opt/venv
COPY content /app/content
RUN useradd --create-home --uid 10001 studio && mkdir -p /data /senseai && chown studio /data
USER studio
WORKDIR /home/studio
EXPOSE 8200
CMD ["sh", "-c", "exec uvicorn senseai_studio.app:app_factory --factory --host 0.0.0.0 --port ${PORT:-8200} --proxy-headers --forwarded-allow-ips='*'"]
