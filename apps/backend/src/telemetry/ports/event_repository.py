"""Porta e modelos de repositório de eventos de telemetria."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from telemetry.domain.entities import TelemetryEvent


@dataclass(frozen=True, slots=True)
class EventFilters:
    """Filtros de busca, cumulativos (RF09).

    Os tres primeiros campos nao sao apenas filtros: sao o que decide qual
    indice do DynamoDB responde a consulta, e portanto quanto ela custa.
    Ver DynamoEventRepository.search.
    """

    session_id: str | None = None
    device_id: str | None = None
    event_name: str | None = None

    # Aplicados depois da query, sobre o que o indice devolveu.
    app_env: str | None = None
    app_target: str | None = None
    app_version: str | None = None
    app_bucket: str | None = None
    device_os: str | None = None
    device_manufacturer: str | None = None
    device_model: str | None = None
    route_path: str | None = None

    occurred_from: datetime | None = None
    occurred_to: datetime | None = None

    limit: int = 50
    # Cursor opaco. Substitui a paginacao por offset: o DynamoDB nao tem OFFSET,
    # ele devolve a chave do ultimo item lido e voce continua dali.
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class QueryStats:
    """Estatísticas de execução e custo da consulta.

    Vai na resposta de proposito. Num banco que cobra por item lido, a
    diferenca entre `scanned` e `returned` e a conta do filtro que roda depois
    da query -- deixar isso visivel evita que uma tela barata e uma tela cara
    parecam iguais.
    """

    strategy: str
    queries: int = 1
    scanned: int = 0
    returned: int = 0


@dataclass(frozen=True, slots=True)
class EventPage:
    """Página resultante de uma busca por eventos com suporte a cursor opaco."""

    items: Sequence[TelemetryEvent]
    next_cursor: str | None = None
    stats: QueryStats | None = None


@dataclass(frozen=True, slots=True)
class EventMetric:
    """Contagem e métricas de agregacao por uma dimensão específica."""

    key: str
    count: int
    average_duration_ms: float | None = None


@dataclass(frozen=True, slots=True)
class TimeBucket:
    """Ponto de agregação da série temporal."""

    bucket: datetime
    count: int
    by_event_name: dict[str, int] = field(default_factory=dict)


class EventRepository(Protocol):
    """Porta de leitura de eventos de telemetria.

    Sem add/delete de proposito: a escrita pertence ao pipeline de ingestao
    (API Gateway -> SQS -> worker), que ja resolve idempotencia, retry e DLQ.
    Uma segunda porta de entrada por aqui significaria duas validacoes para
    manter em sincronia e dois caminhos que divergem com o tempo.
    """

    def search(self, filters: EventFilters) -> EventPage:
        """Busca eventos aplicando filtros cumulativos.

        Args:
            filters (EventFilters): Filtros e opções de paginação.

        Returns:
            EventPage: Página de eventos e metadados.
        """
        ...

    def get(self, session_id: str, event_id: str) -> TelemetryEvent | None:
        """Busca um evento específico por ID de sessão e ID do evento.

        Args:
            session_id (str): Identificador da sessão.
            event_id (str): Identificador do evento.

        Returns:
            TelemetryEvent | None: Instância do evento se encontrado, senão None.
        """
        ...

    def breakdown(
        self, filters: EventFilters, dimension: str, limit: int = 20
    ) -> Sequence[EventMetric]:
        """Agrupa métricas de eventos por uma dimensão específica.

        Args:
            filters (EventFilters): Filtros aplicados à busca.
            dimension (str): Nome da dimensão para agrupamento.
            limit (int, optional): Quantidade máxima de categorias retornadas.

        Returns:
            Sequence[EventMetric]: Lista de métricas agrupadas.
        """
        ...

    def timeseries(self, filters: EventFilters, interval_minutes: int = 60) -> Sequence[TimeBucket]:
        """Agrupa eventos em uma série temporal.

        Args:
            filters (EventFilters): Filtros aplicados à busca.
            interval_minutes (int, optional): Intervalo em minutos para agrupar buckets.

        Returns:
            Sequence[TimeBucket]: Série temporal de buckets.
        """
        ...

    def facets(self, fields: Sequence[str], limit: int = 20) -> dict[str, list[str]]:
        """Obtém valores distintos existentes para preenchimento de opções de filtro.

        Args:
            fields (Sequence[str]): Nomes dos campos solicitados.
            limit (int, optional): Limite de opções retornadas por campo.

        Returns:
            dict[str, list[str]]: Dicionário com lista de opções facetadas por campo.
        """
        ...

    def ping(self) -> bool:
        """Verifica a conectividade e integridade do repositório.

        Returns:
            bool: True se o repositório estiver acessível.
        """
        ...
