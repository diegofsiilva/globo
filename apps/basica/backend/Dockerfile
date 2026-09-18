# syntax=docker/dockerfile:1.7
# O lockfile entra no build para que a imagem use exatamente as dependencias
# revisadas no repositorio, sem resolver novos intervalos a cada publicacao.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY run.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Usuario sem privilegio com uid FIXO, igual ao das outras quatro imagens.
#
# `useradd appuser` sozinho pega o primeiro uid livre (1000 no Debian), e o
# valor deixa de ser uma decisao para virar um detalhe do sistema base. O
# securityContext do Deployment precisa declarar o MESMO numero
# (k8s/base/backend-deployment.yaml): com uid diferente, o processo roda como
# alguem que nao e dono da venv e `HOME` cai para `/`, que e somente-leitura no
# pod. Funciona por sorte enquanto as permissoes forem 755, e quebra em silencio
# no dia em que algo precisar escrever.
RUN groupadd --system --gid 10001 argus \
 && useradd --system --uid 10001 --gid argus --no-create-home argus

COPY --from=builder --chown=argus:argus /app/.venv /app/.venv
COPY --from=builder --chown=argus:argus /app/run.py ./
USER argus

EXPOSE 5000

# O mesmo alvo que a livenessProbe do Kubernetes usa: /health/live responde sem
# tocar no banco, entao ele mede o processo e nao o RDS. Quem checa dependencia
# externa e /health/ready, que vira readinessProbe -- separar os dois impede que
# uma indisponibilidade do banco faca o orquestrador MATAR uma API que esta viva.
#
# `urllib` e nao `curl`: a imagem runtime e python:3.12-slim e nao traz curl nem
# wget, e instalar um deles so para o healthcheck aumentaria a superficie da
# imagem sem necessidade.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/live', timeout=2)"]

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "run:build_app()"]
