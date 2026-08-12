# syntax=docker/dockerfile:1.7
#
# Build para linux/arm64 (Graviton). O Fargate ARM custa ~20% menos que x86 e a
# maquina de desenvolvimento do time e Apple Silicon, entao o build e nativo --
# sem emulacao QEMU, que deixa o build minutos mais lento.
#
#   docker build --platform linux/arm64 -t argus-events-worker:dev worker/

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencias primeiro, em camada propria: mexer no src/ nao invalida o cache
# do pip/uv, que e a parte cara do build.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

# Usuario sem privilegio. O uid fixo permite casar com o do task definition.
RUN groupadd --system --gid 10001 argus \
 && useradd --system --uid 10001 --gid argus --no-create-home argus

COPY --from=builder --chown=argus:argus /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEARTBEAT_PATH=/tmp/argus-worker-heartbeat

WORKDIR /app
USER argus

# O worker toca o heartbeat a cada ciclo. Com long polling de 20s, 120s sem
# toque significa travado de verdade, nao fila vazia.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 120 else 1)"

ENTRYPOINT ["python", "-m", "argus_worker"]
