import json
from collections.abc import Sequence
from datetime import UTC
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from telemetry.domain.entities import TelemetryEvent
from telemetry.ports.event_repository import EventFilters, EventMetric, EventPage


class Base(DeclarativeBase):
    pass


class EventModel(Base):
    __tablename__ = "telemetry_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    event_name: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    app_bucket: Mapped[str | None] = mapped_column(String(80))
    app_env: Mapped[str | None] = mapped_column(String(40))
    app_target: Mapped[str | None] = mapped_column(String(120))
    app_version: Mapped[str | None] = mapped_column(String(40))
    device_id: Mapped[str | None] = mapped_column(String(160))
    device_manufacturer: Mapped[str | None] = mapped_column(String(80))
    device_model: Mapped[str | None] = mapped_column(String(120))
    device_model_year: Mapped[int | None] = mapped_column(Integer)
    device_os: Mapped[str | None] = mapped_column(String(80))
    device_os_version: Mapped[str | None] = mapped_column(String(40))
    session_id: Mapped[str | None] = mapped_column(String(80))
    user_id_hash: Mapped[str | None] = mapped_column(String(64))
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("ix_events_occurred_at", "occurred_at"),
        Index("ix_events_event_name_occurred_at", "event_name", "occurred_at"),
        Index("ix_events_app_target_occurred_at", "app_target", "occurred_at"),
    )


class SqlAlchemyEventRepository:
    FACET_FIELDS = {"event_name", "app_env", "app_target", "device_os", "app_version"}

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def add_many(self, events: Sequence[TelemetryEvent]) -> int:
        if not events:
            return 0
        models = [self._to_model(event) for event in events]
        try:
            with self.session_factory.begin() as session:
                session.add_all(models)
            return len(models)
        except IntegrityError:
            accepted = 0
            for model in models:
                try:
                    with self.session_factory.begin() as session:
                        session.add(model)
                    accepted += 1
                except IntegrityError:
                    # event_id is the idempotency key; a duplicate was already persisted.
                    accepted += 1
                    continue
            return accepted

    def search(self, filters: EventFilters) -> EventPage:
        conditions = self._conditions(filters)

        with self.session_factory() as session:
            total = (
                session.scalar(select(func.count()).select_from(EventModel).where(*conditions)) or 0
            )
            statement = (
                select(EventModel)
                .where(*conditions)
                .order_by(EventModel.occurred_at.desc())
                .offset((filters.page - 1) * filters.page_size)
                .limit(filters.page_size)
            )
            items = [self._to_entity(model) for model in session.scalars(statement)]
        return EventPage(items=items, total=total, page=filters.page, page_size=filters.page_size)

    def metrics(self, filters: EventFilters) -> Sequence[EventMetric]:
        statement = (
            select(
                EventModel.event_name,
                func.count(EventModel.event_id),
                func.avg(EventModel.duration_ms),
            )
            .where(*self._conditions(filters))
            .group_by(EventModel.event_name)
            .order_by(EventModel.event_name)
        )
        with self.session_factory() as session:
            rows = session.execute(statement).all()
        return [
            EventMetric(
                event_name=row[0],
                count=row[1],
                average_duration_ms=float(row[2]) if row[2] is not None else None,
            )
            for row in rows
        ]

    def facets(self, fields: Sequence[str], limit: int = 20) -> dict[str, list[str]]:
        invalid = set(fields) - self.FACET_FIELDS
        if invalid:
            raise ValueError(f"Campos de facet invalidos: {', '.join(sorted(invalid))}")
        result: dict[str, list[str]] = {}
        with self.session_factory() as session:
            for field in fields:
                column = getattr(EventModel, field)
                statement = (
                    select(column)
                    .where(column.is_not(None))
                    .distinct()
                    .order_by(column)
                    .limit(limit)
                )
                result[field] = list(session.scalars(statement))
        return result

    def ping(self) -> bool:
        try:
            with self.session_factory() as session:
                session.execute(select(1))
            return True
        except Exception:
            return False

    @staticmethod
    def _conditions(filters: EventFilters) -> list[Any]:
        conditions = []
        for field in ("event_name", "app_env", "app_target", "device_os"):
            value = getattr(filters, field)
            if value:
                conditions.append(getattr(EventModel, field) == value)
        if filters.occurred_from:
            conditions.append(EventModel.occurred_at >= filters.occurred_from)
        if filters.occurred_to:
            conditions.append(EventModel.occurred_at <= filters.occurred_to)
        return conditions

    @staticmethod
    def _to_model(event: TelemetryEvent) -> EventModel:
        values = {
            field: getattr(event, field)
            for field in EventModel.__table__.columns.keys()
            if field not in {"event_id", "attributes_json"}
        }
        return EventModel(
            event_id=str(event.event_id),
            attributes_json=json.dumps(event.attributes, ensure_ascii=False, separators=(",", ":")),
            **values,
        )

    @staticmethod
    def _to_entity(model: EventModel) -> TelemetryEvent:
        def aware(value: Any) -> Any:
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value

        return TelemetryEvent(
            event_id=UUID(model.event_id),
            schema_version=model.schema_version,
            occurred_at=aware(model.occurred_at),
            received_at=aware(model.received_at),
            event_name=model.event_name,
            duration_ms=model.duration_ms,
            app_bucket=model.app_bucket,
            app_env=model.app_env,
            app_target=model.app_target,
            app_version=model.app_version,
            device_id=model.device_id,
            device_manufacturer=model.device_manufacturer,
            device_model=model.device_model,
            device_model_year=model.device_model_year,
            device_os=model.device_os,
            device_os_version=model.device_os_version,
            session_id=model.session_id,
            user_id_hash=model.user_id_hash,
            attributes=json.loads(model.attributes_json),
        )


def build_repository(database_url: str) -> SqlAlchemyEventRepository:
    if database_url.startswith("sqlite:///"):
        database_path = database_url.removeprefix("sqlite:///")
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(engine)
    return SqlAlchemyEventRepository(sessionmaker(engine, expire_on_commit=False))
