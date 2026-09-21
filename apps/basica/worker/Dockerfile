# syntax=docker/dockerfile:1.7
#
# Imagem dos dois workers de ingestao. O modo (merge ou event) vem do `command`
# da task definition -- ver infra/ecs.tf.
#
# O contexto de build e apps/basica/, e NAO worker/, porque a imagem precisa
# enxergar ../common (o pacote compartilhado). Por isso o -f:
#
#   docker build --platform linux/arm64 \
#     -f worker/Dockerfile -t argus-worker:dev .
#
# Build nativo para linux/arm64 (Graviton): o Fargate ARM custa ~20% menos que
# x86 e a maquina do time e Apple Silicon, entao nao ha emulacao QEMU no meio,
# que deixaria o build minutos mais lento.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencias primeiro, em camada propria: mexer no src/ nao invalida o cache
# do uv, que e a parte cara do build. O common entra inteiro porque e uma
# dependencia de caminho -- o uv precisa dele resolvido ja na primeira sync.
COPY common/ ./common/
COPY worker/pyproject.toml worker/uv.lock ./worker/

WORKDIR /app/worker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY worker/src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS runtime

# Usuario sem privilegio. O uid fixo permite casar com o do task definition.
RUN groupadd --system --gid 10001 argus \
 && useradd --system --uid 10001 --gid argus --no-create-home argus

COPY --from=builder --chown=argus:argus /app/worker/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEARTBEAT_PATH=/tmp/argus-heartbeat

WORKDIR /app
USER argus

# O worker toca o heartbeat a cada ciclo. Com long polling de 20s, 120s sem
# toque significa travado de verdade, nao fila vazia.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 120 else 1)"

ENTRYPOINT ["python", "-m", "argus_worker"]
# Sem CMD padrao de proposito: subir sem escolher o modo seria uma escolha
# silenciosa entre dois workers diferentes. O __main__ recusa e diz o que fazer.
