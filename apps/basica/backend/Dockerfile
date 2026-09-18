FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY run.py ./
RUN pip install --no-cache-dir .

RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

# `--keep-alive 75`: o worker com threads fecha conexao ociosa apos 2 s por
# padrao, e o ALB reutiliza as suas por ate 60 s. Quando o balanceador reaproveita
# uma conexao que o gunicorn acabou de fechar, a requisicao morre em 502 antes de
# chegar ao Flask -- o teste de carga de 17/09/2026 mediu de 1 a 5 por minuto,
# em qualquer nivel de carga. O servidor precisa esperar mais que o balanceador.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--keep-alive", "75", "run:build_app()"]
