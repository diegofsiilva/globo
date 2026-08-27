"""Rota HTTP dos sinais de desvio ativo (tela Agora).

`GET /api/v1/signals` responde a tela Agora (degradacao ativa, baseline,
multiplicador, buckets consecutivos) via `telemetry.application.signals` e
`telemetry.infrastructure.signals`. E uma leitura independente do motor de
hipoteses -- ver docstring de `infrastructure/signals.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify

from telemetry.application.signals import GenerateSignals
from telemetry.interfaces.http import parse_datetime

signals_api = Blueprint("signals_api", __name__, url_prefix="/api/v1")

# Janela padrao bem menor que a de /events (168h): sinal e uma leitura de "o
# que esta acontecendo agora", nao uma busca historica.
JANELA_PADRAO_HORAS = 6


@signals_api.get("/signals")
def listar_sinais():
    """Sinais em desvio ativo AGORA (tela Agora, rotas-frontend.md §4.4.2).

    So entra grupo cujo ULTIMO bucket da janela ainda esta fora do baseline
    -- "ativo agora", nao "desviou em algum momento da janela".
    """
    desde, ate = _janela()
    return jsonify(GenerateSignals(_repository()).execute(desde, ate))


def _janela() -> tuple[datetime, datetime]:
    """Le `from`/`to` da query string, com `to` padrao em `sim.now()`.

    Usa o relogio VIRTUAL (`GoldRepository.clock`), nao o relogio de parede:
    o resto da API (§ `_where` em `postgres.py`) segue a mesma regra, porque
    "agora" para o simulador pode estar replicando uma janela do passado.
    """
    ate = parse_datetime("to")
    desde = parse_datetime("from")
    if ate is None:
        ate = current_app.extensions["gold_repository"].clock().sim_now
    if desde is None:
        desde = ate - timedelta(hours=JANELA_PADRAO_HORAS)
    return desde, ate


def _repository():
    return current_app.extensions["signals_repository"]
