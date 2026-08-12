from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    event_id: UUID
    schema_version: int
    occurred_at: datetime
    received_at: datetime
    event_name: str
    duration_ms: float | None = None
    app_bucket: str | None = None
    app_env: str | None = None
    app_target: str | None = None
    app_version: str | None = None
    device_id: str | None = None
    device_manufacturer: str | None = None
    device_model: str | None = None
    device_model_year: int | None = None
    device_os: str | None = None
    device_os_version: str | None = None
    session_id: str | None = None
    user_id_hash: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
