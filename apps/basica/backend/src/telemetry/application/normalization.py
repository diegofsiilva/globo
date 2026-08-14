"""Módulo de normalização de payloads brutos de telemetria."""

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

from telemetry.domain.entities import TelemetryEvent
from telemetry.domain.exceptions import ValidationError

SUPPORTED_EVENT_NAMES = {"request", "vitals", "screen_view", "video_view", "session", "error"}
SAFE_REQUEST_HEADERS = {
    "accept",
    "content-type",
    "x-client-version",
    "x-platform-id",
    "x-country-code",
}
SENSITIVE_QUERY_KEYS = {"access_token", "authorization", "token", "user_id"}

CSV_FIELD_MAP = {
    "Timestamp": "timestamp",
    "App Bucket": "app_bucket",
    "App Env": "app_env",
    "App Target": "app_target",
    "App Version": "app_version",
    "Device Id": "device_id",
    "Device Manufacturer": "device_manufacturer",
    "Device Model": "device_model",
    "Device Model Year": "device_model_year",
    "Device Os": "device_os",
    "Device Os Version": "device_os_version",
    "Duration": "duration",
    "Event Name": "event_name",
    "Request Headers": "request_headers",
    "Request Method": "request_method",
    "Request Status": "request_status",
    "Request Status Text": "request_status_text",
    "Request Url": "request_url",
    "Response Headers": "response_headers",
    "Route Params": "route_params",
    "Route Path": "route_path",
    "Session Id": "session_id",
    "User Id": "user_id",
}


def canonicalize_keys(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Converte chaves legadas ou em formato CSV para os nomes canônicos de atributos.

    Args:
        payload (Mapping[str, Any]): Dicionário de payload com chaves brutas.

    Returns:
        dict[str, Any]: Dicionário com chaves padronizadas.
    """
    return {CSV_FIELD_MAP.get(key, key): value for key, value in payload.items()}


def normalize_event(
    raw_payload: Mapping[str, Any], *, received_at: datetime, user_id_hash_salt: str
) -> TelemetryEvent:
    """Normaliza um payload bruto para uma instância de TelemetryEvent.

    Args:
        raw_payload (Mapping[str, Any]): Payload original do evento.
        received_at (datetime): Data/hora do recebimento na API.
        user_id_hash_salt (str): Sal para geração de hash do identificador de usuário.

    Returns:
        TelemetryEvent: Evento normalizado.

    Raises:
        ValidationError: Se faltar algum campo obrigatório ou o payload for inválido.
    """
    payload = canonicalize_keys(raw_payload)
    event_name = required_text(payload, "event_name").lower()
    if event_name not in SUPPORTED_EVENT_NAMES:
        raise ValidationError(
            f"event_name deve ser um de: {', '.join(sorted(SUPPORTED_EVENT_NAMES))}",
            field="event_name",
        )

    occurred_at = parse_datetime(payload.get("occurred_at") or payload.get("timestamp"))
    duration = optional_float(payload.get("duration_ms"), "duration_ms")
    if duration is None:
        seconds = optional_float(payload.get("duration"), "duration")
        duration = seconds * 1000 if seconds is not None else None

    event_id = parse_event_id(payload.get("event_id"))
    user_id = optional_text(payload.get("user_id"))
    attributes = build_attributes(payload)

    return TelemetryEvent(
        event_id=event_id,
        schema_version=optional_int(payload.get("schema_version"), "schema_version") or 1,
        occurred_at=occurred_at,
        received_at=received_at,
        event_name=event_name,
        duration_ms=duration,
        app_bucket=optional_text(payload.get("app_bucket")),
        app_env=optional_text(payload.get("app_env")),
        app_target=optional_text(payload.get("app_target")),
        app_version=optional_text(payload.get("app_version")),
        device_id=optional_text(payload.get("device_id")),
        device_manufacturer=optional_text(payload.get("device_manufacturer")),
        device_model=optional_text(payload.get("device_model")),
        device_model_year=optional_int(payload.get("device_model_year"), "device_model_year"),
        device_os=optional_text(payload.get("device_os")),
        device_os_version=optional_text(payload.get("device_os_version")),
        session_id=optional_text(payload.get("session_id")),
        user_id_hash=hash_user_id(user_id, user_id_hash_salt),
        attributes=attributes,
    )


def required_text(payload: Mapping[str, Any], field: str) -> str:
    """Extrai e valida um campo de texto obrigatório.

    Args:
        payload (Mapping[str, Any]): Dicionário de payload.
        field (str): Nome do campo obrigatório.

    Returns:
        str: Valor do campo como texto.

    Raises:
        ValidationError: Se o campo for nulo, vazio ou inexistente.
    """
    value = optional_text(payload.get(field))
    if not value:
        raise ValidationError(f"Campo obrigatorio ausente: {field}", field=field)
    return value


def optional_text(value: Any) -> str | None:
    """Converte um valor para string tratada e limpa ou None se ausente/inválido.

    Args:
        value (Any): Valor original.

    Returns:
        str | None: Texto sanitizado ou None.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text != "***" else None


def optional_float(value: Any, field: str) -> float | None:
    """Converte um valor opcional para float.

    Args:
        value (Any): Valor a ser convertido.
        field (str): Nome do campo para mensagem de erro.

    Returns:
        float | None: Valor numérico convertido ou None.

    Raises:
        ValidationError: Se o valor for texto não numérico.
    """
    value = optional_text(value)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{field} deve ser numerico", field=field) from error


def optional_int(value: Any, field: str) -> int | None:
    """Converte um valor opcional para inteiro.

    Args:
        value (Any): Valor a ser convertido.
        field (str): Nome do campo para mensagem de erro.

    Returns:
        int | None: Valor inteiro convertido ou None.

    Raises:
        ValidationError: Se o valor não for um número inteiro válido.
    """
    value = optional_text(value)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValidationError(f"{field} deve ser inteiro", field=field) from error


def parse_event_id(value: Any) -> UUID:
    """Converte ou gera um UUID para o identificador do evento.

    Args:
        value (Any): Valor bruto recebido para o event_id.

    Returns:
        UUID: Objeto UUID resultante.

    Raises:
        ValidationError: Se o valor fornecido for um UUID inválido.
    """
    if not optional_text(value):
        return uuid4()
    try:
        return UUID(str(value))
    except ValueError as error:
        raise ValidationError("event_id deve ser um UUID", field="event_id") from error


def parse_datetime(value: Any) -> datetime:
    """Converte strings de data/hora ISO ou formatos legados para um objeto datetime em UTC.

    Args:
        value (Any): Valor bruto contendo timestamp.

    Returns:
        datetime: Objeto datetime normalizado em UTC.

    Raises:
        ValidationError: Se o timestamp for nulo ou em formato desconhecido.
    """
    text = optional_text(value)
    if not text:
        raise ValidationError("timestamp ou occurred_at e obrigatorio", field="timestamp")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%B %d, %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValidationError("timestamp invalido", field="timestamp")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_json_object(value: Any, field: str) -> dict[str, Any]:
    """Valida e converte uma string JSON em um dicionário Python.

    Args:
        value (Any): String JSON ou dicionário.
        field (str): Nome do campo para contextualizar erro.

    Returns:
        dict[str, Any]: Objeto JSON parseado.

    Raises:
        ValidationError: Se o JSON for malformado ou não for um objeto.
    """
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as error:
        raise ValidationError(f"{field} deve conter JSON valido", field=field) from error
    if not isinstance(parsed, dict):
        raise ValidationError(f"{field} deve conter um objeto JSON", field=field)
    return parsed


def sanitize_url(value: Any) -> str | None:
    """Higieniza uma URL removendo query params sensíveis.

    Args:
        value (Any): URL bruta.

    Returns:
        str | None: URL sanitizada ou None.
    """
    url = optional_text(value)
    if not url:
        return None
    parts = urlsplit(url)
    safe_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in SENSITIVE_QUERY_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), ""))


def build_attributes(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Constrói o dicionário de atributos dinâmicos do evento.

    Args:
        payload (Mapping[str, Any]): Payload normalizado.

    Returns:
        dict[str, Any]: Dicionário de atributos do evento sem campos bloqueados.
    """
    request_headers = parse_json_object(payload.get("request_headers"), "request_headers")
    safe_headers = {
        str(key).lower(): value
        for key, value in request_headers.items()
        if str(key).lower() in SAFE_REQUEST_HEADERS
    }
    attributes: dict[str, Any] = {}
    candidates = {
        "request_headers": safe_headers,
        "request_method": optional_text(payload.get("request_method")),
        "request_status": optional_int(payload.get("request_status"), "request_status"),
        "request_status_text": optional_text(payload.get("request_status_text")),
        "request_url": sanitize_url(payload.get("request_url")),
        "route_params": parse_json_object(payload.get("route_params"), "route_params"),
        "route_path": optional_text(payload.get("route_path")),
    }
    for key, value in candidates.items():
        if value not in (None, {}, []):
            attributes[key] = value
    extra = payload.get("attributes")
    if extra is not None:
        blocked_keys = {"authorization", "request_headers", "response_headers", "user_id"}
        attributes.update(
            {
                key: value
                for key, value in parse_json_object(extra, "attributes").items()
                if key.lower() not in blocked_keys
            }
        )
    return attributes


def hash_user_id(user_id: str | None, salt: str) -> str | None:
    """Gera hash SHA-256 de um ID de usuário.

    Args:
        user_id (str | None): ID de usuário original.
        salt (str): Sal de segurança.

    Returns:
        str | None: Hash resultante em hexadecimal ou None.
    """
    if not user_id:
        return None
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()
