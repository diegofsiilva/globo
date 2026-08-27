"""Casos de uso de leitura, orientados pelo que o dashboard precisa mostrar.

Cobrem RF08 e RF09 (busca com filtros cumulativos), RF10 (valores para os
filtros), RF11 (agrupamento), RF12 e RF14 (serie temporal e comparacao entre
periodos) e RF16 (linha do tempo de uma sessao para investigacao).

Nao ha caso de uso de escrita: a ingestao pertence ao pipeline
API Gateway -> SQS -> worker.
"""

from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from telemetry.domain.entities import TelemetryEvent
from telemetry.domain.exceptions import EventNotFoundError, ValidationError
from telemetry.ports.event_repository import EventFilters, EventRepository


class SearchEvents:
    """Caso de uso para busca de eventos com filtros cumulativos e paginação (RF08 e RF09)."""

    def __init__(self, repository: EventRepository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository (EventRepository): Instância do repositório de eventos.
        """
        self.repository = repository

    def execute(self, filters: EventFilters) -> dict[str, Any]:
        """Executa a busca de eventos de acordo com os filtros informados.

        Args:
            filters (EventFilters): Filtros cumulativos para a busca.

        Returns:
            dict[str, Any]: Dicionário com os eventos serializados, cursor
                de próxima página e estatísticas da consulta.
        """
        page = self.repository.search(filters)
        return {
            "items": [serialize_event(event) for event in page.items],
            "next_cursor": page.next_cursor,
            "query": asdict(page.stats) if page.stats else None,
        }


class GetSessionTimeline:
    """Todos os eventos de uma sessao, em ordem cronologica (RF16).

    E a consulta mais barata do sistema: uma particao do DynamoDB, ordenada
    pela propria sort key. E tambem a mais util para investigar um incidente,
    porque mostra o que o usuario fez antes do erro.
    """

    def __init__(self, repository: EventRepository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository (EventRepository): Instância do repositório de eventos.
        """
        self.repository = repository

    def execute(self, session_id: str, limit: int = 200) -> dict[str, Any]:
        """Recupera a linha do tempo completa de eventos de uma sessão específica.

        Args:
            session_id (str): Identificador da sessão.
            limit (int, optional): Limite máximo de eventos. Padrão é 200.

        Returns:
            dict[str, Any]: Dicionário contendo os eventos da sessão e o resumo executivo.

        Raises:
            EventNotFoundError: Se nenhum evento for encontrado para a sessão informada.
        """
        page = self.repository.search(EventFilters(session_id=session_id, limit=limit))
        if not page.items:
            raise EventNotFoundError(f"Sessao {session_id} nao encontrada")

        events = sorted(page.items, key=lambda event: event.occurred_at)
        return {
            "session_id": session_id,
            "events": [serialize_event(event) for event in events],
            "summary": summarize(events),
            "next_cursor": page.next_cursor,
            "query": asdict(page.stats) if page.stats else None,
        }


class GetEvent:
    """Caso de uso para obter os detalhes completos de um evento individual por ID e Sessão."""

    def __init__(self, repository: EventRepository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository (EventRepository): Instância do repositório de eventos.
        """
        self.repository = repository

    def execute(self, session_id: str, event_id: str) -> dict[str, Any]:
        """Obtém os dados detalhados de um evento específico.

        Args:
            session_id (str): Identificador da sessão.
            event_id (str): Identificador único do evento.

        Returns:
            dict[str, Any]: Dicionário com os atributos serializados do evento.

        Raises:
            EventNotFoundError: Se o evento não for encontrado.
        """
        event = self.repository.get(session_id, event_id)
        if event is None:
            raise EventNotFoundError(f"Evento {event_id} nao encontrado na sessao {session_id}")
        return serialize_event(event)


class GetBreakdown:
    """Agrupamento por uma dimensao (RF11)."""

    def __init__(self, repository: EventRepository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository (EventRepository): Instância do repositório de eventos.
        """
        self.repository = repository

    def execute(self, filters: EventFilters, dimension: str, limit: int = 20) -> dict[str, Any]:
        """Calcula o agrupamento de eventos por uma dimensão específica.

        Args:
            filters (EventFilters): Filtros aplicados antes do agrupamento.
            dimension (str): Nome da dimensão para agrupamento (ex: 'app_version', 'device_os').
            limit (int, optional): Número máximo de grupos retornados. Padrão é 20.

        Returns:
            dict[str, Any]: Resultado do agrupamento contendo totais e distribuições percentuais.

        Raises:
            ValidationError: Se a dimensão for inválida ou não suportada.
        """
        try:
            groups = self.repository.breakdown(filters, dimension, limit)
        except ValueError as error:
            raise ValidationError(str(error), field="dimension") from error

        total = sum(group.count for group in groups)
        return {
            "dimension": dimension,
            "total": total,
            "groups": [
                {
                    **asdict(group),
                    "share": round(group.count / total, 4) if total else 0.0,
                }
                for group in groups
            ],
        }


class GetCrosstab:
    """Agrupamento por duas dimensões simultaneamente -- heatmap do Recorte (RF16)."""

    def __init__(self, repository: EventRepository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository (EventRepository): Instância do repositório de eventos.
        """
        self.repository = repository

    def execute(
        self, filters: EventFilters, dimension_x: str, dimension_y: str, limit: int = 50
    ) -> dict[str, Any]:
        """Calcula o cruzamento de eventos entre duas dimensões.

        Args:
            filters (EventFilters): Filtros aplicados antes do agrupamento.
            dimension_x (str): Coluna do primeiro eixo.
            dimension_y (str): Coluna do segundo eixo.
            limit (int, optional): Número máximo de células retornadas.

        Returns:
            dict[str, Any]: Dimensões pedidas e as células do cruzamento.

        Raises:
            ValidationError: Se alguma das duas dimensões for inválida.
        """
        try:
            celulas = self.repository.crosstab(filters, dimension_x, dimension_y, limit)
        except ValueError as error:
            raise ValidationError(str(error), field="dimension_x/dimension_y") from error

        return {"dimension_x": dimension_x, "dimension_y": dimension_y, "cells": list(celulas)}


class GetTimeseries:
    """Serie temporal do volume de eventos (RF12).

    Com `compare_previous`, devolve tambem a janela imediatamente anterior de
    mesma duracao e a variacao entre as duas (RF14 e RF15): e o que permite
    dizer "os erros dobraram em relacao a ontem" em vez de so mostrar a curva.
    """

    def __init__(self, repository: EventRepository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository (EventRepository): Instância do repositório de eventos.
        """
        self.repository = repository

    def execute(
        self,
        filters: EventFilters,
        interval_minutes: int = 60,
        compare_previous: bool = False,
    ) -> dict[str, Any]:
        """Gera a série temporal de eventos agregados por intervalo de tempo.

        Args:
            filters (EventFilters): Filtros de consulta.
            interval_minutes (int, optional): Intervalo em minutos para cada bucket. Padrão é 60.
            compare_previous (bool, optional): Se True, inclui comparação com a
                janela de tempo anterior.

        Returns:
            dict[str, Any]: Dados da série temporal com buckets e métricas de variação.

        Raises:
            ValidationError: Se o intervalo for inválido ou se faltar período para comparação.
        """
        try:
            buckets = self.repository.timeseries(filters, interval_minutes)
        except ValueError as error:
            raise ValidationError(str(error), field="interval_minutes") from error

        current_total = sum(bucket.count for bucket in buckets)
        payload: dict[str, Any] = {
            "interval_minutes": interval_minutes,
            "total": current_total,
            "buckets": [
                {
                    "bucket": bucket.bucket.isoformat(),
                    "count": bucket.count,
                    "by_event_name": bucket.by_event_name,
                }
                for bucket in buckets
            ],
        }

        if not compare_previous:
            return payload

        previous_filters = shift_window_back(filters)
        if previous_filters is None:
            raise ValidationError(
                "comparacao com periodo anterior exige 'from' e 'to'", field="compare"
            )
        previous = self.repository.timeseries(previous_filters, interval_minutes)
        previous_total = sum(bucket.count for bucket in previous)

        payload["previous"] = {
            "from": previous_filters.occurred_from.isoformat(),
            "to": previous_filters.occurred_to.isoformat(),
            "total": previous_total,
            "buckets": [
                {"bucket": bucket.bucket.isoformat(), "count": bucket.count} for bucket in previous
            ],
        }
        payload["change"] = {
            "absolute": current_total - previous_total,
            "ratio": (
                round((current_total - previous_total) / previous_total, 4)
                if previous_total
                else None
            ),
        }
        return payload


class GetFacets:
    """Valores existentes para preencher os filtros do dashboard (RF10)."""

    def __init__(self, repository: EventRepository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository (EventRepository): Instância do repositório de eventos.
        """
        self.repository = repository

    def execute(self, fields: Sequence[str], limit: int = 20) -> dict[str, Any]:
        """Obtém opções e valores distintos existentes para os campos solicitados.

        Args:
            fields (Sequence[str]): Lista de campos para extrair os valores facetados.
            limit (int, optional): Quantidade máxima de valores por campo. Padrão é 20.

        Returns:
            dict[str, Any]: Dicionário mapeando cada campo à sua lista de valores facetados.

        Raises:
            ValidationError: Se algum dos campos especificados for inválido.
        """
        try:
            return {"facets": self.repository.facets(fields, limit)}
        except ValueError as error:
            raise ValidationError(str(error), field="field") from error


# ---------------------------------------------------------------------- #
# Auxiliares
# ---------------------------------------------------------------------- #


def shift_window_back(filters: EventFilters) -> EventFilters | None:
    """Mesma janela, deslocada para trás pela própria duração.

    Args:
        filters (EventFilters): Objeto de filtros original contendo occurred_from e occurred_to.

    Returns:
        EventFilters | None: Novos filtros com a janela deslocada ou None se o período for inválido.
    """
    if not filters.occurred_from or not filters.occurred_to:
        return None
    span = filters.occurred_to - filters.occurred_from
    if span <= timedelta(0):
        return None
    return replace_window(
        filters,
        start=filters.occurred_from - span,
        end=filters.occurred_from,
    )


def replace_window(filters: EventFilters, *, start: datetime, end: datetime) -> EventFilters:
    """Substitui o intervalo de tempo em um objeto de filtros mantendo os demais campos.

    Args:
        filters (EventFilters): Filtros originais.
        start (datetime): Nova data/hora inicial.
        end (datetime): Nova data/hora final.

    Returns:
        EventFilters: Nova instância de EventFilters com a nova janela temporal.
    """
    values = {field: getattr(filters, field) for field in filters.__slots__}
    values["occurred_from"] = start
    values["occurred_to"] = end
    return EventFilters(**values)


def summarize(events: Sequence[TelemetryEvent]) -> dict[str, Any]:
    """Resumo da sessão: o cabeçalho da tela de investigação.

    Args:
        events (Sequence[TelemetryEvent]): Lista sequencial de eventos de uma mesma sessão.

    Returns:
        dict[str, Any]: Resumo estatístico da sessão com totais, datas e metadados do aparelho.
    """
    if not events:
        return {}
    counts: dict[str, int] = {}
    for event in events:
        counts[event.event_name] = counts.get(event.event_name, 0) + 1
    first, last = events[0], events[-1]
    return {
        "event_count": len(events),
        "by_event_name": counts,
        "error_count": counts.get("error", 0),
        "started_at": first.occurred_at.isoformat(),
        "ended_at": last.occurred_at.isoformat(),
        "duration_seconds": round((last.occurred_at - first.occurred_at).total_seconds(), 3),
        "device": {
            "manufacturer": first.device_manufacturer,
            "model": first.device_model,
            "os": first.device_os,
            "os_version": first.device_os_version,
        },
        "app": {
            "target": first.app_target,
            "version": first.app_version,
            "env": first.app_env,
        },
    }


def serialize_event(event: TelemetryEvent) -> dict[str, Any]:
    """Serializa uma instância de TelemetryEvent para formato dicionário/JSON.

    Args:
        event (TelemetryEvent): Instância da entidade de evento de telemetria.

    Returns:
        dict[str, Any]: Dicionário contendo os dados do evento com datas em formato ISO 8601.
    """
    data = asdict(event)
    data["occurred_at"] = event.occurred_at.isoformat()
    data["ingested_at"] = event.ingested_at.isoformat() if event.ingested_at else None
    return data
