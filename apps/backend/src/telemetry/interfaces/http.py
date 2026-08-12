"""Rotas HTTP da API de leitura.

Somente leitura. Nao ha POST nem DELETE: a entrada de eventos e o pipeline
API Gateway -> SQS -> worker, que ja resolve idempotencia, retry e DLQ, e o
expurgo e feito pelo TTL do DynamoDB -- a task role do worker nem tem
permissao de DeleteItem.
"""

from datetime import datetime
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from telemetry.application.use_cases import (
    GetBreakdown,
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
                "timeseries": "GET /api/v1/metrics/timeseries?interval=60&compare=true",
                "facets": "GET /api/v1/facets?field=event_name&field=app_target",
                "health": "GET /health/ready",
                "docs": "GET /docs",
                "openapi": "GET /openapi.json",
            },
            "notes": "Ingestao nao passa por aqui: use o endpoint do API Gateway.",
        }
    )


@health.get("/favicon.ico")
def favicon():
    return "", 204


@health.get("/openapi.json")
def openapi_spec():
    """Especificacao da API. O campo `servers` vem do host desta requisicao."""
    return jsonify(build_spec())


@health.get("/docs")
def swagger_ui():
    """Swagger UI apontando para /openapi.json."""
    return Response(SWAGGER_UI, mimetype="text/html")


@api.get("/events")
def search_events():
    return jsonify(SearchEvents(repository()).execute(filters_from_query()))


@api.get("/sessions/<session_id>")
def session_timeline(session_id: str):
    limit = parse_int("limit", default=200, minimum=1, maximum=1000)
    return jsonify(GetSessionTimeline(repository()).execute(session_id, limit))


@api.get("/sessions/<session_id>/events/<event_id>")
def event_detail(session_id: str, event_id: str):
    return jsonify(GetEvent(repository()).execute(session_id, event_id))


@api.get("/devices/<device_id>")
def device_history(device_id: str):
    filters = filters_from_query()
    values = {field: getattr(filters, field) for field in filters.__slots__}
    values["device_id"] = device_id
    return jsonify(SearchEvents(repository()).execute(EventFilters(**values)))


@api.get("/metrics/breakdown")
def breakdown():
    dimension = request.args.get("dimension")
    if not dimension:
        raise ValidationError("parametro 'dimension' e obrigatorio", field="dimension")
    limit = parse_int("limit", default=20, minimum=1, maximum=100)
    return jsonify(GetBreakdown(repository()).execute(filters_from_query(), dimension, limit))


@api.get("/metrics/timeseries")
def timeseries():
    interval = parse_int("interval", default=60, minimum=1, maximum=1440)
    compare = request.args.get("compare", "").lower() in {"1", "true", "yes"}
    return jsonify(
        GetTimeseries(repository()).execute(filters_from_query(), interval, compare)
    )


@api.get("/facets")
def facets():
    fields = request.args.getlist("field") or [
        "event_name",
        "app_env",
        "app_target",
        "device_os",
        "device_manufacturer",
    ]
    limit = parse_int("limit", default=20, minimum=1, maximum=100)
    return jsonify(GetFacets(repository()).execute(fields, limit))


@health.get("/health/live")
def liveness():
    return jsonify({"status": "ok"})


@health.get("/health/ready")
def readiness():
    ready = repository().ping()
    return jsonify({"status": "ok" if ready else "unavailable"}), 200 if ready else 503


# ---------------------------------------------------------------------- #
# Parsing dos parametros
# ---------------------------------------------------------------------- #


def filters_from_query() -> EventFilters:
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
        occurred_from=parse_datetime("from"),
        occurred_to=parse_datetime("to"),
        limit=parse_int("limit", default=50, minimum=1, maximum=500),
        cursor=request.args.get("cursor"),
    )


def parse_datetime(name: str) -> datetime | None:
    value = request.args.get(name)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"parametro '{name}' deve ser ISO 8601", field=name) from error


def parse_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
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
    return current_app.extensions["event_repository"]
