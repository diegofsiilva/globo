"""Rotas HTTP de eventos e telemetria agregada."""

from datetime import datetime, timedelta
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from telemetry.application.use_cases import (
    GetBreakdown,
    GetCrosstab,
    GetEvent,
    GetFacets,
    GetSessionTimeline,
    GetTimeseries,
    SearchEvents,
)
from telemetry.domain.exceptions import ValidationError
from telemetry.interfaces.openapi import SWAGGER_UI, build_spec
from telemetry.ports.event_repository import EventFilters

api = Blueprint("api", __name__, url_prefix="/api/v1")
health = Blueprint("health", __name__)


@health.get("/")
def index():
    """Endpoint raiz da API fornecendo informações básicas e lista de rotas principais."""
    return jsonify(
        {
            "service": "telemetry-read-api",
            "status": "ok",
            "message": "API de leitura dos eventos de telemetria",
            "endpoints": {
                "search": "GET /api/v1/events",
                "session_timeline": "GET /api/v1/sessions/{session_id}",
                "event_detail": "GET /api/v1/sessions/{session_id}/events/{event_id}",
                "device_history": "GET /api/v1/devices/{device_id}",
                "breakdown": "GET /api/v1/metrics/breakdown?dimension=app_target",
                "crosstab": "GET /api/v1/metrics/crosstab?dimension_x=device_model&dimension_y=uf",
                "timeseries": "GET /api/v1/metrics/timeseries?interval=60&compare=true",
                "facets": "GET /api/v1/facets?field=event_name&field=app_target",
                "signals": "GET /api/v1/signals?from&to",
                "changes": "GET /api/v1/changes?from&to",
                "timeline": "GET /api/v1/timeline?from&to",
                "stable_window": "GET /api/v1/references/stable-window?duration_minutes&before",
                "last_live_peak": "GET /api/v1/references/last-live-peak?before",
                "health": "GET /health/ready",
                "docs": "GET /docs",
                "openapi": "GET /openapi.json",
                "hypotheses": "GET /api/v1/hypotheses",
                "hypothesis_runs": "GET /api/v1/hypothesis-runs",
            },
            "notes": "Ingestao nao passa por aqui: use o endpoint do API Gateway.",
        }
    )


@health.get("/favicon.ico")
def favicon():
    """Endpoint de favicon para requisições do navegador (retorna 204 No Content)."""
    return "", 204


@health.get("/openapi.json")
def openapi_spec():
    """Especificação OpenAPI 3.1 da API. O campo `servers` vem do host desta requisição."""
    return jsonify(build_spec())


@health.get("/docs")
def swagger_ui():
    """Serve a interface gráfica do Swagger UI, apontando para /openapi.json."""
    return Response(SWAGGER_UI, mimetype="text/html")


@api.get("/events")
def search_events():
    """Endpoint para busca paginada de eventos de telemetria com filtros cumulativos."""
    return jsonify(SearchEvents(repository()).execute(filters_from_query()))


@api.get("/sessions/<session_id>")
def session_timeline(session_id: str):
    """Endpoint para obtenção da linha do tempo completa de eventos de uma determinada sessão."""
    limit = parse_int("limit", default=200, minimum=1, maximum=1000)
    return jsonify(GetSessionTimeline(repository()).execute(session_id, limit))


@api.get("/sessions/<session_id>/events/<event_id>")
def event_detail(session_id: str, event_id: str):
    """Endpoint para consultar os detalhes de um evento específico por ID de sessão e evento."""
    return jsonify(GetEvent(repository()).execute(session_id, event_id))


@api.get("/devices/<device_id>")
def device_history(device_id: str):
    """Endpoint para buscar o histórico de eventos de um dispositivo específico."""
    filters = filters_from_query()
    values = {field: getattr(filters, field) for field in filters.__slots__}
    values["device_id"] = device_id
    return jsonify(SearchEvents(repository()).execute(EventFilters(**values)))


@api.get("/metrics/breakdown")
def breakdown():
    """Endpoint de agrupamento métrico de eventos por uma dimensão específica."""
    dimension = request.args.get("dimension")
    if not dimension:
        raise ValidationError("parametro 'dimension' e obrigatorio", field="dimension")
    limit = parse_int("limit", default=20, minimum=1, maximum=100)
    return jsonify(GetBreakdown(repository()).execute(filters_from_query(), dimension, limit))


@api.get("/metrics/crosstab")
def crosstab():
    """Endpoint de cruzamento entre duas dimensoes -- heatmap do Recorte (RF16)."""
    dimension_x = request.args.get("dimension_x")
    dimension_y = request.args.get("dimension_y")
    if not dimension_x or not dimension_y:
        raise ValidationError(
            "parametros 'dimension_x' e 'dimension_y' sao obrigatorios", field="dimension_x"
        )
    limit = parse_int("limit", default=50, minimum=1, maximum=200)
    return jsonify(
        GetCrosstab(repository()).execute(filters_from_query(), dimension_x, dimension_y, limit)
    )


@api.get("/metrics/timeseries")
def timeseries():
    """Endpoint para obtenção da série temporal de volume de eventos e comparações temporais."""
    interval = parse_int("interval", default=60, minimum=1, maximum=1440)
    compare = request.args.get("compare", "").lower() in {"1", "true", "yes"}
    return jsonify(GetTimeseries(repository()).execute(filters_from_query(), interval, compare))


@api.get("/facets")
def facets():
    """Endpoint para consultar as opções e valores existentes de filtros facetados."""
    fields = request.args.getlist("field") or [
        "event_name",
        "app_env",
        "app_target",
        "device_os",
        "device_manufacturer",
    ]
    limit = parse_int("limit", default=20, minimum=1, maximum=100)
    return jsonify(GetFacets(repository()).execute(fields, limit))


# ---------------------------------------------------------------------- #
# Camada gold: o que as telas de serie consultam
# ---------------------------------------------------------------------- #


@api.get("/clock")
def clock():
    """Devolve o instante VIRTUAL, que e o "agora" de todas as telas.

    Sem esta rota, o dashboard usaria o relogio do navegador como "agora" -- e
    as telas apareceriam vazias sem explicar por que, porque o simulador pode
    estar replicando uma janela de julho enquanto o navegador marca agosto.
    """
    agora = gold().clock()
    return jsonify(
        {
            "sim_now": agora.sim_now.isoformat(),
            "speed": agora.speed,
            "updated_at": agora.updated_at.isoformat(),
        }
    )


@api.get("/series")
def series():
    """Serie de telemetria em bucket de 15 min, vinda de gold.v_feature_bucket."""
    pontos = gold().series(
        source=request.args.get("source") or None,
        entity=request.args.get("entity") or None,
        metric=request.args.get("metric") or None,
        desde=parse_datetime("from"),
        ate=parse_datetime("to"),
        janela_horas=parse_int("window_hours", default=24, minimum=1, maximum=8760),
        limite=parse_int("limit", default=5000, minimum=1, maximum=20000),
    )
    return jsonify(
        {
            "items": [
                {
                    "bucket_ts": ponto["bucket_ts"].isoformat(),
                    "source": ponto["source"],
                    "entity": ponto["entity"],
                    "metric": ponto["metric"],
                    "value": ponto["value"],
                    "hora_brt": ponto["hora_brt"],
                    "dow": ponto["dow"],
                    "tem_jogo": ponto["tem_jogo"],
                }
                for ponto in pontos
            ],
            "count": len(pontos),
        }
    )


@api.get("/sources")
def sources():
    """Fontes disponiveis e quao recente esta cada uma."""
    return jsonify(
        {
            "items": [
                {
                    "source": linha["source"],
                    "entidades": linha["entidades"],
                    "metricas": linha["metricas"],
                    "ultimo_bucket": (
                        linha["ultimo_bucket"].isoformat() if linha["ultimo_bucket"] else None
                    ),
                }
                for linha in gold().sources()
            ]
        }
    )


@api.get("/incidents")
def incidents():
    """Janelas de incidente do ground truth.

    Por padrao EXCLUI os rotulos `detector-derived`: sete dos vinte foram
    criados olhando a saida do proprio Argus, e avaliar um detector novo contra
    eles mede concordancia com o baseline, nao acuracia. Quem quiser inclui-los
    precisa pedir com `?include_derived=true`, de forma explicita.
    """
    janelas = gold().incidents(
        origem=request.args.get("origem") or None,
        incluir_derivados=request.args.get("include_derived", "").lower() in {"1", "true", "yes"},
        limite=parse_int("limit", default=100, minimum=1, maximum=1000),
    )
    return jsonify(
        {
            "items": [
                {
                    "window_id": j["window_id"],
                    "ts_start": j["ts_start"].isoformat(),
                    "ts_end": j["ts_end"].isoformat(),
                    "origem": j["origem"],
                    "ref_id": j["ref_id"],
                    "verdict": j["verdict"],
                    "severity": j["severity"],
                    "provenance": j["provenance"],
                }
                for j in janelas
            ],
            "count": len(janelas),
        }
    )


@api.get("/live-events")
def live_events():
    """Calendario de transmissoes, com os feeds simultaneos agregados por confronto."""
    eventos = gold().live_events(limite=parse_int("limit", default=50, minimum=1, maximum=500))
    return jsonify(
        {
            "items": [
                {
                    "event_key": e["event_key"],
                    "ts_start": e["ts_start"].isoformat(),
                    "ts_end": e["ts_end"].isoformat(),
                    "competition": e["competition"],
                    "team_home": e["team_home"],
                    "team_away": e["team_away"],
                    "feeds": e["feeds"],
                }
                for e in eventos
            ],
            "count": len(eventos),
        }
    )


@api.get("/changes")
def changes():
    """Eventos de mudanca de plataforma (deploy) na janela.

    So cobre deploy (fonte Tsuru): o dataset nao tem log discreto de mudanca
    para autoscale nem WAF, so serie de metrica -- ver 018_deploy_events.sql.
    """
    return jsonify(
        {
            "items": [
                {
                    **item,
                    "started_at": item["started_at"].isoformat(),
                    "ended_at": item["ended_at"].isoformat() if item["ended_at"] else None,
                }
                for item in gold().deploy_events(
                    desde=parse_datetime("from"),
                    ate=parse_datetime("to"),
                    limite=parse_int("limit", default=200, minimum=1, maximum=2000),
                )
            ]
        }
    )


@api.get("/references/stable-window")
def stable_window():
    """Janela de referencia para 'ultima janela estavel' (tela Comparar).

    Devolve `from`/`to` de uma janela recente sem sobreposicao com
    `gold.v_incident_window`; o cliente usa o par como `from`/`to` de uma
    segunda chamada a `/metrics/timeseries`.
    """
    duracao = timedelta(minutes=parse_int("duration_minutes", default=60, minimum=1, maximum=1440))
    antes = parse_datetime("before") or gold().clock().sim_now
    janela = gold().janela_estavel(duracao=duracao, antes=antes)
    if janela is None:
        return jsonify({"found": False})
    return jsonify(
        {"found": True, "from": janela["ts_start"].isoformat(), "to": janela["ts_end"].isoformat()}
    )


@api.get("/references/last-live-peak")
def last_live_peak():
    """Janela de referencia para 'pico ao vivo anterior' (tela Comparar)."""
    antes = parse_datetime("before") or gold().clock().sim_now
    evento = gold().ultimo_pico_ao_vivo(antes=antes)
    if evento is None:
        return jsonify({"found": False})
    return jsonify(
        {
            "found": True,
            "event_key": evento["event_key"],
            "from": evento["ts_start"].isoformat(),
            "to": evento["ts_end"].isoformat(),
            "competition": evento["competition"],
            "team_home": evento["team_home"],
            "team_away": evento["team_away"],
        }
    )


LANES_METRICA = {
    "npaw": {"label": "NPAW", "sources": ["npaw", "youbora", "youbora_player_live"]},
    "prometheus": {"label": "Prometheus", "sources": ["prometheus"]},
    "newrelic": {"label": "New Relic", "sources": ["newrelic"]},
    "apollo": {"label": "Apollo", "sources": ["apollo"]},
}


@api.get("/timeline")
def timeline():
    """Seis raias de fonte (rotas-frontend.md §4.4.6).

    Quatro raias de serie de metrica (NPAW, Prometheus, New Relic, Apollo),
    uma de deploy (Tsuru, `gold.v_deploy_event`) e uma de incidente
    (ServiceNow, `gold.v_incident_window` com origem `incidents`).
    `lane_type` muda por raia de proposito -- forcar deploy e incidente no
    formato de serie temporal perderia duracao, motivo e gravidade. Nome
    `lane_type` (nao `kind`) de proposito: o mock do frontend ja usa `kind`
    para o ESTADO de cada barra (`deploy`/`critical`/`neutral`/`empty`), um
    conceito diferente -- reusar o nome ia confundir quem escrever o adapter.
    """
    ate = parse_datetime("to") or gold().clock().sim_now
    desde = parse_datetime("from") or (ate - timedelta(hours=3))

    lanes = []
    for chave, config in LANES_METRICA.items():
        pontos = gold().lane_series(config["sources"], desde, ate)
        lanes.append(
            {
                "source": chave,
                "label": config["label"],
                "lane_type": "series",
                "points": [
                    {
                        "bucket_ts": p["bucket_ts"].isoformat(),
                        "entity": p["entity"],
                        "metric": p["metric"],
                        "value": p["value"],
                    }
                    for p in pontos
                ],
            }
        )

    lanes.append(
        {
            "source": "tsuru",
            "label": "Tsuru",
            "lane_type": "events",
            "points": [
                {
                    **evento,
                    "started_at": evento["started_at"].isoformat(),
                    "ended_at": evento["ended_at"].isoformat() if evento["ended_at"] else None,
                }
                for evento in gold().deploy_events(desde=desde, ate=ate, limite=500)
            ],
        }
    )

    lanes.append(
        {
            "source": "servicenow",
            "label": "ServiceNow",
            "lane_type": "incidents",
            "points": [
                {
                    **incidente,
                    "ts_start": incidente["ts_start"].isoformat(),
                    "ts_end": incidente["ts_end"].isoformat(),
                }
                for incidente in gold().incidents(
                    origem="incidents", desde=desde, ate=ate, limite=500
                )
            ],
        }
    )

    return jsonify({"window": {"from": desde.isoformat(), "to": ate.isoformat()}, "lanes": lanes})


@api.get("/anomalies")
def anomalies():
    """Anomalias da execucao mais recente do detector.

    Devolve lista vazia enquanto nao houver detector (decisao 7 do plano). A
    rota existe desde ja para que o dashboard seja escrito contra o contrato
    final, e nao precise mudar quando a deteccao chegar.
    """
    run_id = request.args.get("run_id")
    itens = gold().anomalies(
        run_id=int(run_id) if run_id and run_id.isdigit() else None,
        limite=parse_int("limit", default=200, minimum=1, maximum=2000),
    )
    return jsonify(
        {
            "items": [{**item, "bucket_ts": item["bucket_ts"].isoformat()} for item in itens],
            "count": len(itens),
        }
    )


@health.get("/health/live")
def liveness():
    """Endpoint de verificação de liveness da aplicação para a infraestrutura de orquestração."""
    return jsonify({"status": "ok"})


@health.get("/health/ready")
def readiness():
    """Endpoint de verificação de readiness checando a conexão com o repositório."""
    ready = repository().ping()
    return jsonify({"status": "ok" if ready else "unavailable"}), 200 if ready else 503


# ---------------------------------------------------------------------- #
# Parsing dos parametros
# ---------------------------------------------------------------------- #


def filters_from_query() -> EventFilters:
    """Extrai e constrói um objeto EventFilters a partir dos parâmetros da Query String HTTP.

    Returns:
        EventFilters: Objeto contendo os filtros parseados.
    """
    return EventFilters(
        session_id=request.args.get("session_id"),
        device_id=request.args.get("device_id"),
        event_name=request.args.get("event_name"),
        app_env=request.args.get("app_env"),
        app_target=request.args.get("app_target"),
        app_version=request.args.get("app_version"),
        app_bucket=request.args.get("app_bucket"),
        device_os=request.args.get("device_os"),
        device_manufacturer=request.args.get("device_manufacturer"),
        device_model=request.args.get("device_model"),
        route_path=request.args.get("route_path"),
        uf=request.args.get("uf"),
        isp=request.args.get("isp"),
        occurred_from=parse_datetime("from"),
        occurred_to=parse_datetime("to"),
        limit=parse_int("limit", default=50, minimum=1, maximum=500),
        cursor=request.args.get("cursor"),
    )


def parse_datetime(name: str) -> datetime | None:
    """Extrai e valida um parâmetro de data/hora ISO 8601 da query string.

    Args:
        name (str): Nome do parâmetro de busca.

    Returns:
        datetime | None: Data/hora em datetime UTC ou None.

    Raises:
        ValidationError: Se o parâmetro contiver formato inválido.
    """
    value = request.args.get(name)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"parametro '{name}' deve ser ISO 8601", field=name) from error


def parse_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    """Extrai e valida um parâmetro numérico inteiro dentro de um intervalo.

    Args:
        name (str): Nome do parâmetro na query string.
        default (int): Valor padrão caso ausente.
        minimum (int): Limite mínimo aceitável.
        maximum (int): Limite máximo aceitável.

    Returns:
        int: Valor numérico inteiro validado.

    Raises:
        ValidationError: Se o parâmetro não for inteiro ou estiver fora da faixa permitida.
    """
    value = request.args.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValidationError(f"parametro '{name}' deve ser inteiro", field=name) from error
    if parsed < minimum or parsed > maximum:
        raise ValidationError(
            f"parametro '{name}' deve estar entre {minimum} e {maximum}", field=name
        )
    return parsed


def repository() -> Any:
    """Obtém a instância atual do repositório de eventos vinculada à extensão do Flask.

    Returns:
        Any: Instância do repositório de eventos.
    """
    return current_app.extensions["event_repository"]


def gold() -> Any:
    """Obtém o repositório da camada gold (séries, janelas e relógio virtual).

    Returns:
        Any: Instância do repositório de gold.
    """
    return current_app.extensions["gold_repository"]
