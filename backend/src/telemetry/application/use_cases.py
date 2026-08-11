from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from telemetry.application.normalization import normalize_event
from telemetry.domain.exceptions import ValidationError
from telemetry.ports.event_repository import EventFilters, EventRepository


@dataclass(frozen=True, slots=True)
class RejectedEvent:
    index: int
    code: str
    message: str
    field: str | None


@dataclass(frozen=True, slots=True)
class IngestionResult:
    accepted: int
    rejected: int
    errors: Sequence[RejectedEvent]


class IngestEvents:
    def __init__(self, repository: EventRepository, user_id_hash_salt: str) -> None:
        self.repository = repository
        self.user_id_hash_salt = user_id_hash_salt

    def execute(self, payloads: Sequence[Mapping[str, Any]]) -> IngestionResult:
        now = datetime.now(UTC)
        events = []
        errors = []
        for index, payload in enumerate(payloads, start=1):
            try:
                events.append(
                    normalize_event(
                        payload,
                        received_at=now,
                        user_id_hash_salt=self.user_id_hash_salt,
                    )
                )
            except ValidationError as error:
                errors.append(
                    RejectedEvent(
                        index=index,
                        code="VALIDATION_ERROR",
                        message=str(error),
                        field=error.field,
                    )
                )

        accepted = self.repository.add_many(events) if events else 0
        return IngestionResult(accepted=accepted, rejected=len(errors), errors=errors)


class SearchEvents:
    def __init__(self, repository: EventRepository) -> None:
        self.repository = repository

    def execute(self, filters: EventFilters) -> dict[str, Any]:
        result = self.repository.search(filters)
        return {
            "items": [serialize_event(item) for item in result.items],
            "pagination": {
                "page": result.page,
                "page_size": result.page_size,
                "total": result.total,
            },
        }


class GetMetrics:
    def __init__(self, repository: EventRepository) -> None:
        self.repository = repository

    def execute(self, filters: EventFilters) -> dict[str, Any]:
        groups = self.repository.metrics(filters)
        return {
            "total": sum(group.count for group in groups),
            "by_event_name": [asdict(group) for group in groups],
        }


def serialize_event(event: Any) -> dict[str, Any]:
    data = asdict(event)
    data["event_id"] = str(event.event_id)
    data["occurred_at"] = event.occurred_at.isoformat()
    data["received_at"] = event.received_at.isoformat()
    return data
