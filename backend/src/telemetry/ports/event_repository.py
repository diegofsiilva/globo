from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from telemetry.domain.entities import TelemetryEvent


@dataclass(frozen=True, slots=True)
class EventFilters:
    event_name: str | None = None
    app_env: str | None = None
    app_target: str | None = None
    device_os: str | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    page: int = 1
    page_size: int = 50


@dataclass(frozen=True, slots=True)
class EventPage:
    items: Sequence[TelemetryEvent]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class EventMetric:
    event_name: str
    count: int
    average_duration_ms: float | None


class EventRepository(Protocol):
    def add_many(self, events: Sequence[TelemetryEvent]) -> int: ...

    def search(self, filters: EventFilters) -> EventPage: ...

    def facets(self, fields: Sequence[str], limit: int = 20) -> dict[str, list[str]]: ...

    def metrics(self, filters: EventFilters) -> Sequence[EventMetric]: ...

    def ping(self) -> bool: ...
