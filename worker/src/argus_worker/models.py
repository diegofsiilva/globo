"""Schemas dos eventos de telemetria do app de TV.

Seis tipos de evento sao conhecidos hoje (request, screen_view, session,
video_view, vitals, error), mas o modelo e deliberadamente permissivo:

  - `extra="allow"`: campo novo enviado pelo app e preservado, nao rejeitado.
  - Tipo de evento desconhecido cai em `GenericEvent` em vez de virar erro.
  - So quatro campos sao obrigatorios (timestamp, event_name, session_id,
    device_id) -- o resto e opcional.

O motivo e operacional: o parque de TVs atualiza devagar e de forma desigual, e
um modelo estrito transformaria qualquer mudanca de schema no app em perda de
dados em massa, sem chance de hotfix. Aqui a gente aceita, grava e sinaliza:
campos recomendados ausentes viram a metrica EventsIncomplete, e tipo novo vira
EventsUnknownType. Validacao vira observabilidade, nao descarte.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #


class BaseEvent(BaseModel):
    """Envelope comum a todo evento."""

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    timestamp: datetime
    event_name: str
    session_id: str
    device_id: str

    # Contexto do app
    app_bucket: str | None = None
    app_env: str | None = None
    app_target: str | None = None
    app_version: str | None = None
    app_resolution: str | None = None

    # Contexto do device
    device_manufacturer: str | None = None
    device_model: str | None = None
    device_model_year: int | str | None = None
    device_os: str | None = None
    device_os_version: str | None = None
    device_resolution: str | None = None
    device_user_agent: str | None = None

    # Comuns a quase todos
    user_id: str | None = None
    duration: float | None = None
    action: str | None = None
    route_path: str | None = None
    route_params: dict[str, Any] | str | None = None

    # Idempotencia: se o cliente mandar, respeitamos; se nao, derivamos do
    # conteudo em keys.build_event_id.
    event_id: str | None = None

    @field_validator("timestamp", mode="after")
    @classmethod
    def _to_utc(cls, value: datetime) -> datetime:
        """Timestamp sem timezone e tratado como UTC em vez de rejeitado."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("session_id", "device_id", mode="after")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value:
            raise ValueError("nao pode ser vazio")
        return value


# --------------------------------------------------------------------------- #
# Tipos conhecidos
# --------------------------------------------------------------------------- #


class RequestEvent(BaseEvent):
    """Chamada HTTP feita pelo app (latencia, status, rota)."""

    event_name: Literal["request"] = "request"
    request_method: str | None = None
    request_url: str | None = None
    request_status: int | None = None
    request_status_text: str | None = None
    request_headers: dict[str, Any] | str | None = None
    response_headers: dict[str, Any] | str | None = None


class ScreenViewEvent(BaseEvent):
    """Entrada em uma tela do app."""

    event_name: Literal["screen_view"] = "screen_view"


class SessionEvent(BaseEvent):
    """Ciclo de vida da sessao, com as capabilities negociadas do device."""

    event_name: Literal["session"] = "session"
    capabilities_audio_dolby_atmos: bool | None = None
    capabilities_cursor: bool | None = None
    capabilities_https: bool | None = None
    capabilities_motion: bool | None = None
    capabilities_video_hdr: bool | None = None
    capabilities_video_live_drm: bool | None = None
    capabilities_video_vod_drm: bool | None = None


class VideoViewEvent(BaseEvent):
    """Reproducao de video (live ou vod)."""

    event_name: Literal["video_view"] = "video_view"
    media_id: str | int | None = None
    media_kind: str | None = None
    media_ads: bool | None = None
    media_drm: bool | None = None


class VitalsEvent(BaseEvent):
    """Sinal de saude do player/app -- travamento, buffering etc."""

    event_name: Literal["vitals"] = "vitals"


class ErrorEvent(BaseEvent):
    """Erro exibido ao usuario."""

    event_name: Literal["error"] = "error"
    error_name: str | None = None
    error_message: str | None = None
    error_stack: str | None = None


class GenericEvent(BaseEvent):
    """Fallback para event_name que ainda nao conhecemos.

    Valida so o envelope e guarda o resto via extra="allow". Existe para que um
    evento novo no app apareca no DynamoDB no mesmo dia em que for lancado, em
    vez de acumular na DLQ ate alguem mexer no worker.
    """


EVENT_TYPES: dict[str, type[BaseEvent]] = {
    "request": RequestEvent,
    "screen_view": ScreenViewEvent,
    "session": SessionEvent,
    "video_view": VideoViewEvent,
    "vitals": VitalsEvent,
    "error": ErrorEvent,
}

KNOWN_EVENT_NAMES = frozenset(EVENT_TYPES)


def parse_event(raw: dict[str, Any]) -> tuple[BaseEvent, bool]:
    """Valida um evento cru.

    Devolve (evento, is_known). `is_known` False significa que caiu no
    GenericEvent -- o dado e gravado do mesmo jeito, mas contabilizado.
    Levanta pydantic.ValidationError se nem o envelope basico bater.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"evento precisa ser objeto JSON, recebi {type(raw).__name__}")

    name = raw.get("event_name")
    model = EVENT_TYPES.get(name) if isinstance(name, str) else None
    if model is None:
        return GenericEvent.model_validate(raw), False
    return model.model_validate(raw), True
