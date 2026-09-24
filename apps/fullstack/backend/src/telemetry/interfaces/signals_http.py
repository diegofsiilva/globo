"""Rota HTTP dos sinais de desvio ativo (tela Agora).

`GET /api/v1/signals` responde a tela Agora (degradacao ativa, baseline,
multiplicador, buckets consecutivos) via `telemetry.application.signals` e
`telemetry.infrastructure.signals`. E uma leitura independente do motor de
hipoteses -- ver docstring de `infrastructure/signals.py`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, current_app, jsonify, request

from telemetry.application.signals import LIMITE_MAXIMO, LIMITE_PADRAO, GenerateSignals
from telemetry.domain.exceptions import ValidationError
from telemetry.infrastructure.signals import SignalsRepository
from telemetry.interfaces.http import parse_datetime, parse_int

signals_api = Blueprint("signals_api", __name__, url_prefix="/api/v1")

# Janela padrao bem menor que a de /events (168h): sinal e uma leitura de "o
# que esta acontecendo agora", nao uma busca historica.
JANELA_PADRAO_HORAS = 6


@signals_api.get("/signals")
def listar_sinais():
    """Sinais em desvio ativo AGORA (tela Agora, rotas-frontend.md §4.4.2).

    So entra grupo cujo ULTIMO bucket da janela ainda esta fora do baseline
    -- "ativo agora", nao "desviou em algum momento da janela".

    Aceita os mesmos filtros de dimensao das demais telas (`source`, `entity`,
    `metric`, `tem_jogo`) e um `limit` (padrao 25, maximo 100). A resposta traz
    `count` e `truncated` para que a tela saiba que existe mais do que coube.
    """
    desde, ate = _janela()
    limite = parse_int("limit", default=LIMITE_PADRAO, minimum=1, maximum=LIMITE_MAXIMO)
    try:
        return jsonify(
            GenerateSignals(_repository()).execute(desde, ate, escopo=_escopo(), limite=limite)
        )
    except ValueError as error:
        raise ValidationError(str(error), field="source") from error


def _escopo() -> dict[str, str]:
    """Le os filtros de dimensao aceitos pela tela Agora.

    Mesma regra de `http._escopo_da_query`: um parametro repetido representa
    uma lista, e nao deve virar igualdade pelo primeiro valor -- a tela cairia
    num recorte que o operador nao pediu, sem nada na interface indicando isso.

    Returns:
        dict[str, str]: Dimensao -> valor unico informado.
    """
    escopo = {}
    for dimensao in SignalsRepository.DIMENSOES:
        valores = [valor for valor in request.args.getlist(dimensao) if valor]
        if len(valores) == 1:
            escopo[dimensao] = valores[0]
    return escopo


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
    """Obtém o repositório de sinais registrado na aplicação.

    Returns:
        SignalsRepository: A instância montada em `create_app`, ou o dublê que
            o teste injetou no lugar dela.
    """
    return current_app.extensions["signals_repository"]
