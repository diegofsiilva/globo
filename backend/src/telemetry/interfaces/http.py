import csv
import io
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from telemetry.application.use_cases import GetMetrics, IngestEvents, SearchEvents
from telemetry.domain.exceptions import UnsupportedMediaTypeError, ValidationError
from telemetry.ports.event_repository import EventFilters

api = Blueprint("api", __name__, url_prefix="/api/v1")
health = Blueprint("health", __name__)


@api.post("/events")
def ingest_events():
    payloads = parse_request_payload()
    use_case = IngestEvents(repository(), current_app.config["USER_ID_HASH_SALT"])
    result = use_case.execute(payloads)
    response = {
        "accepted": result.accepted,
        "rejected": result.rejected,
        "errors": [
            {
                "row": error.index,
                "code": error.code,
                "message": error.message,
                "field": error.field,
            }
            for error in result.errors
        ],
    }
    status = 201 if result.accepted and not result.rejected else 207 if result.accepted else 422
    return jsonify(response), status


@api.get("/events")
def search_events():
    return jsonify(SearchEvents(repository()).execute(filters_from_query()))


@api.get("/metrics")
def metrics():
    return jsonify(GetMetrics(repository()).execute(filters_from_query()))


def filters_from_query() -> EventFilters:
    return EventFilters(
        event_name=request.args.get("event_name"),
        app_env=request.args.get("app_env"),
        app_target=request.args.get("app_target"),
        device_os=request.args.get("device_os"),
        occurred_from=parse_query_datetime("from"),
        occurred_to=parse_query_datetime("to"),
        page=parse_positive_int("page", default=1, maximum=1_000_000),
        page_size=parse_positive_int("page_size", default=50, maximum=200),
    )


@api.get("/events/facets")
def event_facets():
    fields = request.args.getlist("field") or ["event_name", "app_env", "app_target", "device_os"]
    try:
        return jsonify({"facets": repository().facets(fields)})
    except ValueError as error:
        raise ValidationError(str(error), field="field") from error


@health.get("/health/live")
def liveness():
    return jsonify({"status": "ok"})


@health.get("/health/ready")
def readiness():
    ready = repository().ping()
    return jsonify({"status": "ok" if ready else "unavailable"}), 200 if ready else 503


def parse_request_payload() -> list[Mapping[str, Any]]:
    if request.mimetype == "text/csv":
        text = request.get_data(as_text=True)
        try:
            payloads = list(csv.DictReader(io.StringIO(text)))
        except csv.Error as error:
            raise ValidationError("CSV invalido") from error
        if not payloads:
            raise ValidationError("CSV deve conter ao menos um evento")
        return payloads

    if request.is_json:
        payload = request.get_json()
        if isinstance(payload, dict) and "events" in payload:
            payload = payload["events"]
        if isinstance(payload, dict):
            return [payload]
        if (
            payload
            and isinstance(payload, list)
            and all(isinstance(item, dict) for item in payload)
        ):
            return payload
        raise ValidationError("JSON deve ser um evento, uma lista ou um objeto com events")

    raise UnsupportedMediaTypeError("Use application/json ou text/csv")


def parse_query_datetime(name: str) -> datetime | None:
    value = request.args.get(name)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"Parametro {name} deve ser ISO 8601", field=name) from error
    return parsed


def parse_positive_int(name: str, *, default: int, maximum: int) -> int:
    value = request.args.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValidationError(f"Parametro {name} deve ser inteiro", field=name) from error
    if parsed < 1 or parsed > maximum:
        raise ValidationError(f"Parametro {name} deve estar entre 1 e {maximum}", field=name)
    return parsed


def repository():
    return current_app.extensions["event_repository"]
