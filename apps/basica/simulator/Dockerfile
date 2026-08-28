# syntax=docker/dockerfile:1.7
#
# Imagem do servico `simulator`.
#
# O contexto de build e apps/basica/, e NAO simulator/, porque a imagem precisa
# enxergar ../common (o pacote compartilhado). Por isso o -f:
#
#   docker build --platform linux/arm64 \
#     -f simulator/Dockerfile -t argus-simulator:dev .
#
# Build nativo para linux/arm64 (Graviton): o Fargate ARM custa ~20% menos que
# x86 e a maquina do time e Apple Silicon, entao nao ha emulacao QEMU no meio.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencias primeiro, em camada propria: mexer no src/ nao invalida o cache
# do uv, que e a parte cara do build. O common entra inteiro porque e uma
# dependencia de caminho -- o uv precisa dele resolvido ja na primeira sync.
COPY common/ ./common/
COPY simulator/pyproject.toml simulator/uv.lock ./simulator/

WORKDIR /app/simulator
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY simulator/src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

# Usuario sem privilegio. O uid fixo permite casar com o do task definition.
RUN groupadd --system --gid 10001 argus \
 && useradd --system --uid 10001 --gid argus --no-create-home argus

COPY --from=builder --chown=argus:argus /app/simulator/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEARTBEAT_PATH=/tmp/argus-heartbeat

WORKDIR /app
USER argus

# Toca o heartbeat a cada ciclo. 120s sem toque significa travado de verdade.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 120 else 1)"

ENTRYPOINT ["python", "-m", "argus_simulator"]
