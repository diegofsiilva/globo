"""Adaptador de leitura do DynamoDB.

Implementa a porta EventRepository sobre a tabela unica que o worker de
ingestao escreve. O desenho de chaves e dado, nao escolhido aqui:

    tabela  pk=SESSION#<session_id>                sk=<ts>#<event_id[:12]>
    GSI1    gsi1pk=EVT#<event_name>#<data>#<shard> gsi1sk=<ts>#<event_id[:12]>
    GSI2    gsi2pk=DEV#<device_id>                 gsi2sk=<ts>#<event_id[:12]>

O ponto que governa o custo de toda consulta e QUAL desses caminhos ela
consegue usar. Ver `search`.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from telemetry.application.redaction import hash_user_id, redact_attributes
from telemetry.domain.entities import TelemetryEvent
from telemetry.domain.exceptions import ValidationError
from telemetry.ports.event_repository import (
    EventFilters,
    EventMetric,
    EventPage,
    QueryStats,
    TimeBucket,
)

log = logging.getLogger(__name__)

# Campos que sao atributo de primeira classe da entidade. O resto do item vai
# para `attributes`.
CORE_FIELDS = frozenset(
    {
        "event_id",
        "event_name",
        "timestamp",
        "ingested_at",
        "session_id",
        "device_id",
        "user_id",
        "duration",
        "action",
        "route_path",
        "app_bucket",
        "app_env",
        "app_target",
        "app_version",
        "app_resolution",
        "device_manufacturer",
        "device_model",
        "device_model_year",
        "device_os",
        "device_os_version",
        "device_resolution",
        "clock_skew",
    }
)

# Chaves internas do modelo de dados. Nao interessam a quem consome a API.
KEY_FIELDS = frozenset(
    {
        "pk",
        "sk",
        "gsi1pk",
        "gsi1sk",
        "gsi2pk",
        "gsi2sk",
        "event_date",
        "expires_at",
        "clock_skew_days",
    }
)

# Filtros que viram FilterExpression: aplicados pelo DynamoDB DEPOIS da query,
# entao eles reduzem o que trafega mas nao o que e lido (e cobrado).
POST_FILTERS = (
    "app_env",
    "app_target",
    "app_version",
    "app_bucket",
    "device_os",
    "device_manufacturer",
    "device_model",
    "route_path",
)

FACET_FIELDS = frozenset(
    {
        "event_name",
        "app_env",
        "app_target",
        "app_version",
        "app_bucket",
        "device_os",
        "device_manufacturer",
        "device_model",
        "route_path",
    }
)

BREAKDOWN_FIELDS = FACET_FIELDS | {"device_model_year"}


class DynamoEventRepository:
    """Adaptador de leitura do DynamoDB que implementa a porta `EventRepository`.

    Traduz os filtros do dashboard no caminho de acesso mais barato disponível
    (Query na tabela, na GSI1 com fan-out por shard/dia, na GSI2, ou Scan como
    último recurso) e converte os itens crus em `TelemetryEvent` já redigido.

    Os limites de `max_items_scanned` e `max_days_fanout` existem para dar teto
    ao custo de uma requisição: num banco que cobra por item lido, uma consulta
    sem filtro poderia varrer a tabela inteira.
    """

    def __init__(
        self,
        table,
        *,
        gsi1_shards: int = 10,
        user_id_hash_salt: str = "",
        max_items_scanned: int = 20_000,
        max_days_fanout: int = 31,
        default_window_hours: int = 168,
        max_workers: int = 16,
        table_factory: Callable[[], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Inicializa o repositório de leitura.

        Args:
            table: Recurso de tabela do boto3 (`dynamodb.Table`).
            gsi1_shards (int, optional): Número de shards da GSI1, que precisa
                bater com o que o worker usa na escrita. Padrão é 10.
            user_id_hash_salt (str, optional): Sal aplicado ao `user_id` na
                conversão para entidade.
            max_items_scanned (int, optional): Teto de itens lidos por consulta.
                Padrão é 20.000.
            max_days_fanout (int, optional): Máximo de dias abertos em paralelo
                no fan-out da GSI1. Padrão é 31.
            default_window_hours (int, optional): Janela usada quando a consulta
                não informa período. Padrão é 168 (7 dias).
            max_workers (int, optional): Teto de queries paralelas. Padrão é 16.
            table_factory (Callable[[], Any] | None, optional): Fábrica de tabela
                por thread; sem ela, o recurso do boto3 é compartilhado.
            clock (Callable[[], datetime] | None, optional): Fonte do "agora"
                usada para fechar a janela de uma consulta sem período. Existe
                para o teste poder fixar a data: com o relógio real, um teste
                sobre dado de data fixa passa hoje e falha quando o dado sai do
                recorte de `max_days_fanout` — falha por passagem do tempo, não
                por regressão. Padrão é `datetime.now(UTC)`.
        """
        self._table = table
        self._shards = max(1, gsi1_shards)
        self._salt = user_id_hash_salt
        self._max_items = max_items_scanned
        self._max_days = max_days_fanout
        self._default_window = timedelta(hours=default_window_hours)
        self._max_workers = max(1, max_workers)
        self._table_factory = table_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._local = threading.local()

    # ------------------------------------------------------------------ #
    # Leitura pontual
    # ------------------------------------------------------------------ #

    def get(self, session_id: str, event_id: str) -> TelemetryEvent | None:
        """Busca um evento dentro de uma sessao.

        Exige session_id porque a chave da tabela e (sessao, tempo+id) -- nao
        existe caminho para achar um evento so pelo event_id sem varrer tudo
        ou criar mais um indice. A rota da API reflete isso:
        /sessions/<sid>/events/<eid>.
        """
        response = self._table.query(
            KeyConditionExpression=Key("pk").eq(f"SESSION#{session_id}"),
            FilterExpression=Attr("event_id").eq(event_id),
            Limit=200,
        )
        items = response.get("Items", [])
        return self._to_entity(items[0]) if items else None

    def ping(self) -> bool:
        """Verifica se a tabela responde, para o readiness probe.

        Returns:
            bool: True se o `describe_table` respondeu; False em qualquer erro,
                que é registrado no log em vez de propagado.
        """
        try:
            self._table.load()
            return True
        except Exception:
            log.warning("dynamodb indisponivel", exc_info=True)
            return False

    # ------------------------------------------------------------------ #
    # Busca
    # ------------------------------------------------------------------ #

    def search(self, filters: EventFilters) -> EventPage:
        """Escolhe o caminho de acesso mais barato que os filtros permitem.

        Em ordem de custo crescente:

          1. session_id  -> Query na tabela. Uma particao, exato.
          2. device_id   -> Query na GSI2. Uma particao.
          3. event_name  -> Query na GSI1, com fan-out nos shards e nos dias do
                            periodo. N queries em paralelo, cada uma barata.
          4. nenhum      -> Scan com filtro. Le a tabela inteira.

        O caso 4 e o unico que nao escala, e ele existe porque nao ha
        alternativa: sem event_name nao ha chave de particao, e fazer fan-out
        pelos tipos conhecidos deixaria de fora os tipos novos que o pipeline
        aceita de proposito (o worker grava event_name desconhecido em vez de
        recusar). Preferimos ler demais a esconder evento.
        """
        cursor = _decode_cursor(filters.cursor)

        if filters.session_id:
            return self._query_partitions(
                filters,
                [(None, Key("pk").eq(f"SESSION#{filters.session_id}"))],
                index=None,
                strategy="table:session",
                cursor=cursor,
            )

        if filters.device_id:
            return self._query_partitions(
                filters,
                [(None, Key("gsi2pk").eq(f"DEV#{filters.device_id}"))],
                index="gsi2",
                strategy="gsi2:device",
                cursor=cursor,
            )

        if filters.event_name:
            partitions = self._gsi1_partitions(filters)
            return self._query_partitions(
                filters,
                partitions,
                index="gsi1",
                strategy="gsi1:fanout",
                cursor=cursor,
            )

        return self._scan(filters, cursor)

    # ------------------------------------------------------------------ #
    # Agregacao
    # ------------------------------------------------------------------ #

    def breakdown(
        self, filters: EventFilters, dimension: str, limit: int = 20
    ) -> Sequence[EventMetric]:
        """Agrupa por uma dimensao e conta (RF11).

        A agregacao acontece aqui, em memoria, e nao no banco: o DynamoDB nao
        tem GROUP BY. O custo e ler o periodo inteiro para contar. Funciona no
        volume atual; num volume de producao o caminho seria manter contadores
        pre-agregados alimentados por DynamoDB Streams.
        """
        if dimension not in BREAKDOWN_FIELDS:
            raise ValueError(
                f"dimensao invalida: {dimension}. Use uma de: {', '.join(sorted(BREAKDOWN_FIELDS))}"
            )

        events = self._collect(filters)
        counts: Counter[str] = Counter()
        durations: defaultdict[str, list[float]] = defaultdict(list)

        for event in events:
            value = getattr(event, dimension, None)
            if value is None:
                value = event.attributes.get(dimension)
            key = "(sem valor)" if value is None else str(value)
            counts[key] += 1
            if event.duration_ms is not None:
                durations[key].append(event.duration_ms)

        return [
            EventMetric(
                key=key,
                count=count,
                average_duration_ms=(
                    round(sum(durations[key]) / len(durations[key]), 3) if durations[key] else None
                ),
            )
            for key, count in counts.most_common(limit)
        ]

    def timeseries(self, filters: EventFilters, interval_minutes: int = 60) -> Sequence[TimeBucket]:
        """Serie temporal do volume de eventos (RF12, base para RF14 e RF15)."""
        if interval_minutes < 1:
            raise ValueError("interval_minutes deve ser >= 1")

        events = self._collect(filters)
        step = timedelta(minutes=interval_minutes)
        buckets: defaultdict[datetime, Counter[str]] = defaultdict(Counter)

        for event in events:
            moment = event.occurred_at.astimezone(UTC)
            offset = (
                moment - moment.replace(hour=0, minute=0, second=0, microsecond=0)
            ).total_seconds()
            start = moment.replace(hour=0, minute=0, second=0, microsecond=0) + step * int(
                offset // step.total_seconds()
            )
            buckets[start][event.event_name] += 1

        return [
            TimeBucket(
                bucket=start,
                count=sum(names.values()),
                by_event_name=dict(names),
            )
            for start, names in sorted(buckets.items())
        ]

    def facets(self, fields: Sequence[str], limit: int = 20) -> dict[str, list[str]]:
        """Valores existentes para preencher os filtros (RF10).

        Sem indice que responda "valores distintos", isso e um scan projetado
        so nas colunas pedidas -- barato em trafego, caro em itens lidos. Um
        cache curto na frente resolveria; deixado de fora enquanto o volume
        nao justifica.
        """
        invalid = set(fields) - FACET_FIELDS
        if invalid:
            raise ValueError(
                f"campos de facet invalidos: {', '.join(sorted(invalid))}. "
                f"Use: {', '.join(sorted(FACET_FIELDS))}"
            )

        found: defaultdict[str, set[str]] = defaultdict(set)
        scanned = 0
        kwargs: dict[str, Any] = {
            "ProjectionExpression": ", ".join(f"#{f}" for f in fields),
            "ExpressionAttributeNames": {f"#{f}": f for f in fields},
        }

        while scanned < self._max_items:
            response = self._table.scan(**kwargs)
            for item in response.get("Items", []):
                scanned += 1
                for name in fields:
                    value = item.get(name)
                    if value is not None:
                        found[name].add(str(value))
            start = response.get("LastEvaluatedKey")
            if not start:
                break
            kwargs["ExclusiveStartKey"] = start

        return {name: sorted(found[name])[:limit] for name in fields}

    # ------------------------------------------------------------------ #
    # Execucao das consultas
    # ------------------------------------------------------------------ #

    def _gsi1_partitions(self, filters: EventFilters) -> list[tuple[str, Any]]:
        """Uma particao por (dia, shard) do periodo consultado.

        Quando o periodo excede `_max_days`, mantemos os dias MAIS RECENTES e
        descartamos os antigos. O sentido do corte importa: a busca devolve do
        mais novo para o mais antigo, entao truncar pelo comeco faria uma
        consulta de um ano varrer os 31 primeiros dias e nao encontrar nada do
        mes atual -- resultado vazio, sem erro, com o dado bem ali.
        """
        start, end = self._window(filters)
        first_day, last_day = start.date(), end.date()

        days: list[Any] = []
        day = last_day
        while day >= first_day and len(days) < self._max_days:
            days.append(day)
            day -= timedelta(days=1)

        partitions: list[tuple[str, Any]] = []
        for day in days:
            for shard in range(self._shards):
                pk = f"EVT#{filters.event_name}#{day.isoformat()}#{shard}"
                partitions.append((pk, Key("gsi1pk").eq(pk)))

        return partitions

    def _query_partitions(
        self,
        filters: EventFilters,
        partitions: list[tuple[str | None, Any]],
        *,
        index: str | None,
        strategy: str,
        cursor: dict[str, Any],
    ) -> EventPage:
        """Consulta várias partições em paralelo e funde o resultado numa página.

        Cada partição tem seu próprio ponto de retomada dentro do cursor, então
        a paginação continua exatamente de onde parou mesmo com o fan-out.

        Args:
            filters (EventFilters): Filtros da consulta, incluindo o `limit`.
            partitions (list[tuple[str | None, Any]]): Pares (id da partição,
                KeyConditionExpression) a consultar.
            index (str | None): Nome do índice secundário, ou None para a tabela.
            strategy (str): Rótulo do caminho de acesso, reportado em `QueryStats`.
            cursor (dict[str, Any]): Estado de retomada por partição; o valor
                "done" marca partição já esgotada.

        Returns:
            EventPage: Itens ordenados do mais recente para o mais antigo, com
                o cursor da próxima página e as estatísticas de custo.
        """
        # Na GSI1 o event_name ja e chave da particao; nas outras rotas ele
        # precisa entrar como filtro.
        condition = self._filter_expression(filters, include_event_name=(index != "gsi1"))
        collected: list[tuple[dict[str, Any], TelemetryEvent, str]] = []
        scanned = 0
        executed = 0
        exhausted: set[str] = set()
        read_per_partition: Counter[str] = Counter()

        pending: list[tuple[str, dict[str, Any]]] = []
        for name, key_condition in partitions:
            partition_id = name or "_"
            if cursor.get(partition_id) == "done":
                exhausted.add(partition_id)
                continue

            kwargs: dict[str, Any] = {
                "KeyConditionExpression": key_condition,
                "ScanIndexForward": False,  # mais recente primeiro
                "Limit": max(filters.limit, 1),
            }
            if index:
                kwargs["IndexName"] = index
            if condition is not None:
                kwargs["FilterExpression"] = condition
            start_key = cursor.get(partition_id)
            if isinstance(start_key, dict):
                kwargs["ExclusiveStartKey"] = start_key
            pending.append((partition_id, kwargs))

        for partition_id, response in self._run_queries(pending):
            executed += 1
            items = response.get("Items", [])
            scanned += response.get("ScannedCount", len(items))

            for item in items:
                event = self._to_entity(item)
                if self._within_window(event, filters):
                    collected.append((item, event, partition_id))
                    read_per_partition[partition_id] += 1

            if not response.get("LastEvaluatedKey"):
                exhausted.add(partition_id)

        collected.sort(key=lambda row: (row[1].occurred_at, row[1].event_id), reverse=True)
        page = collected[: filters.limit]

        next_cursor = self._next_cursor(
            page, partitions, exhausted, read_per_partition, cursor, index
        )

        return EventPage(
            items=[event for _, event, _ in page],
            next_cursor=next_cursor,
            stats=QueryStats(
                strategy=strategy,
                queries=executed,
                scanned=scanned,
                returned=len(page),
            ),
        )

    def _run_queries(
        self, pending: list[tuple[str, dict[str, Any]]]
    ) -> list[tuple[str, dict[str, Any]]]:
        """Executa as queries do fan-out em paralelo.

        Cada particao e uma ida independente ao DynamoDB, e o fan-out de uma
        semana chega a 80 delas (7 dias x 10 shards + 1). Em sequencia isso
        somava 11 segundos de latencia de rede -- quatro vezes o teto de 3s do
        RNF02 -- com o banco praticamente ocioso, porque o custo era o
        round-trip e nao o trabalho.

        Cada thread usa a propria instancia de Table: recurso do boto3 nao tem
        garantia de ser thread-safe, e o cliente por baixo tem pool de conexao
        proprio.
        """
        if len(pending) <= 1:
            return [(partition_id, self._table.query(**kwargs)) for partition_id, kwargs in pending]

        workers = min(self._max_workers, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._query_one, kwargs): partition_id
                for partition_id, kwargs in pending
            }
            return [(futures[future], future.result()) for future in as_completed(futures)]

    def _query_one(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Executa uma Query usando a Table da thread corrente.

        Args:
            kwargs (dict[str, Any]): Argumentos já montados para `Table.query`.

        Returns:
            dict[str, Any]: Resposta crua do DynamoDB.
        """
        return self._thread_table().query(**kwargs)

    def _thread_table(self):
        """Table desta thread, criada sob demanda."""
        if self._table_factory is None:
            return self._table
        table = getattr(self._local, "table", None)
        if table is None:
            table = self._table_factory()
            self._local.table = table
        return table

    def _next_cursor(
        self,
        page: list[tuple[dict[str, Any], TelemetryEvent, str]],
        partitions: list[tuple[str | None, Any]],
        exhausted: set[str],
        read_per_partition: Counter[str],
        previous: dict[str, Any],
        index: str | None,
    ) -> str | None:
        """Onde cada particao parou, para a proxima pagina continuar dali.

        Guarda o ultimo item EFETIVAMENTE devolvido de cada particao, nao o
        ultimo lido. Com fan-out, cada particao devolve ate `limit` itens mas
        so alguns entram na pagina depois do merge por tempo; retomar pelo
        ultimo lido pularia os que ficaram de fora.

        Uma particao so e marcada "done" quando o DynamoDB nao tem mais paginas
        E tudo que veio dela ja foi emitido. Esgotada no banco nao e o mesmo
        que consumida -- confundir as duas descartava os itens ainda pendentes.
        """
        emitted_per_partition: Counter[str] = Counter()
        last_emitted: dict[str, dict[str, Any]] = {}
        for item, _, partition_id in page:
            emitted_per_partition[partition_id] += 1
            last_emitted[partition_id] = item

        state: dict[str, Any] = {}
        for name, _ in partitions:
            partition_id = name or "_"
            emitted = emitted_per_partition[partition_id]
            read = read_per_partition[partition_id]

            if partition_id in exhausted and emitted >= read:
                state[partition_id] = "done"
                continue

            item = last_emitted.get(partition_id)
            if item is not None:
                state[partition_id] = _key_of(item, index)
            elif partition_id in previous:
                # Nada desta particao entrou na pagina: mantem onde ela estava
                # para que os itens pendentes sejam reconsiderados na proxima.
                state[partition_id] = previous[partition_id]

        # A comparacao e contra TODAS as particoes, nao contra as que estao no
        # state: particao com item pendente e sem nada emitido nesta pagina nao
        # ganha entrada nenhuma, e olhar so o state faria a paginacao terminar
        # com evento por devolver.
        every_partition = {name or "_" for name, _ in partitions}
        finished = {pid for pid, value in state.items() if value == "done"}
        if not page or finished == every_partition:
            return None
        return _encode_cursor(state)

    def _scan(self, filters: EventFilters, cursor: dict[str, Any]) -> EventPage:
        """Ultimo recurso: sem chave de particao, so resta varrer.

        A paginacao aqui e por deslocamento, e nao pelo LastEvaluatedKey do
        DynamoDB. O motivo e que o Scan devolve os itens em ordem de hash, nao
        de tempo: para responder "os mais recentes primeiro" e preciso ler o
        conjunto inteiro e ordenar. Retomar pela chave do banco entregaria a
        pagina seguinte da ordem ERRADA e pularia os itens que a ordenacao
        tinha deixado para depois.

        Consequencia honesta: cada pagina relê o conjunto. Aceitavel no volume
        do MVP e transparente via `stats.scanned`. O caminho para nao pagar
        isso e sempre informar `event_name`, `session_id` ou `device_id`, que
        levam a uma Query indexada.
        """
        condition = self._filter_expression(filters, include_event_name=True)
        collected: list[TelemetryEvent] = []
        scanned = 0
        pages = 0

        kwargs: dict[str, Any] = {}
        if condition is not None:
            kwargs["FilterExpression"] = condition

        while scanned < self._max_items:
            response = self._table.scan(**kwargs)
            pages += 1
            scanned += response.get("ScannedCount", 0)
            for item in response.get("Items", []):
                event = self._to_entity(item)
                if self._within_window(event, filters):
                    collected.append(event)
            start_key = response.get("LastEvaluatedKey")
            if not start_key:
                break
            kwargs["ExclusiveStartKey"] = start_key

        collected.sort(key=lambda event: (event.occurred_at, event.event_id), reverse=True)

        offset = cursor.get("_offset", 0)
        if not isinstance(offset, int) or offset < 0:
            raise ValidationError("cursor invalido ou expirado", field="cursor")

        page = collected[offset : offset + filters.limit]
        next_offset = offset + len(page)
        next_cursor = (
            _encode_cursor({"_offset": next_offset}) if next_offset < len(collected) else None
        )

        return EventPage(
            items=page,
            next_cursor=next_cursor,
            stats=QueryStats(
                strategy="table:scan",
                queries=pages,
                scanned=scanned,
                returned=len(page),
            ),
        )

    def _collect(self, filters: EventFilters) -> list[TelemetryEvent]:
        """Puxa o conjunto inteiro do periodo para agregar em memoria."""
        events: list[TelemetryEvent] = []
        cursor = None
        budget = self._max_items

        while budget > 0:
            page = self.search(
                EventFilters(
                    **{
                        **{
                            field: getattr(filters, field)
                            for field in filters.__slots__
                            if field not in {"limit", "cursor"}
                        },
                        "limit": min(500, budget),
                        "cursor": cursor,
                    }
                )
            )
            events.extend(page.items)
            budget -= max(len(page.items), 1)
            cursor = page.next_cursor
            if not cursor or not page.items:
                break

        return events

    # ------------------------------------------------------------------ #
    # Auxiliares
    # ------------------------------------------------------------------ #

    def _window(self, filters: EventFilters) -> tuple[datetime, datetime]:
        """Resolve a janela temporal efetiva da consulta.

        Sem período informado, aplica `default_window_hours` para trás: uma
        consulta sem recorte viraria uma varredura da tabela inteira.

        Args:
            filters (EventFilters): Filtros com o período opcional.

        Returns:
            tuple[datetime, datetime]: Par (início, fim) da janela.
        """
        end = filters.occurred_to or self._clock()
        start = filters.occurred_from or (end - self._default_window)
        return start, end

    def _within_window(self, event: TelemetryEvent, filters: EventFilters) -> bool:
        """Confere se o evento cai dentro do período pedido.

        Args:
            event (TelemetryEvent): Evento já convertido.
            filters (EventFilters): Filtros com os limites do período.

        Returns:
            bool: True se o evento está dentro da janela (ou se ela é aberta).
        """
        if filters.occurred_from and event.occurred_at < filters.occurred_from:
            return False
        if filters.occurred_to and event.occurred_at > filters.occurred_to:
            return False
        return True

    def _filter_expression(self, filters: EventFilters, *, include_event_name: bool = False):
        """Monta a FilterExpression dos campos que nao sao chave de indice.

        `include_event_name` so e verdadeiro no scan e nas queries por sessao e
        por aparelho. Na GSI1 o event_name ja esta embutido na chave da
        particao, e repeti-lo como filtro seria custo sem ganho.
        """
        fields = POST_FILTERS + (("event_name",) if include_event_name else ())
        condition = None
        for field in fields:
            value = getattr(filters, field, None)
            if not value:
                continue
            clause = Attr(field).eq(value)
            condition = clause if condition is None else condition & clause
        return condition

    def _to_entity(self, item: dict[str, Any]) -> TelemetryEvent:
        """Converte um item cru do DynamoDB na entidade de domínio.

        É aqui que a redação acontece na leitura: o `user_id` vira hash e os
        atributos passam por `redact_attributes` antes de sair do adaptador,
        então nenhuma camada acima vê o dado sensível.

        Args:
            item (dict[str, Any]): Item cru como o boto3 devolveu.

        Returns:
            TelemetryEvent: Entidade com os campos já normalizados e redigidos.
        """
        attributes = {
            key: _plain(value)
            for key, value in item.items()
            if key not in CORE_FIELDS and key not in KEY_FIELDS
        }

        duration = item.get("duration")
        return TelemetryEvent(
            event_id=str(item.get("event_id", "")),
            event_name=str(item.get("event_name", "unknown")),
            occurred_at=_parse_datetime(item.get("timestamp")),
            ingested_at=_parse_optional_datetime(item.get("ingested_at")),
            session_id=str(item.get("session_id", "")),
            device_id=str(item.get("device_id", "")),
            # O DynamoDB guarda segundos, como o app envia. O dashboard usa ms.
            duration_ms=round(float(duration) * 1000, 3) if duration is not None else None,
            action=_text(item.get("action")),
            route_path=_text(item.get("route_path")),
            app_bucket=_text(item.get("app_bucket")),
            app_env=_text(item.get("app_env")),
            app_target=_text(item.get("app_target")),
            app_version=_text(item.get("app_version")),
            app_resolution=_text(item.get("app_resolution")),
            device_manufacturer=_text(item.get("device_manufacturer")),
            device_model=_text(item.get("device_model")),
            device_model_year=_plain(item.get("device_model_year")),
            device_os=_text(item.get("device_os")),
            device_os_version=_text(item.get("device_os_version")),
            device_resolution=_text(item.get("device_resolution")),
            user_id_hash=hash_user_id(_text(item.get("user_id")), self._salt),
            clock_skew=bool(item.get("clock_skew", False)),
            attributes=redact_attributes(attributes),
        )


# ---------------------------------------------------------------------- #
# Conversao e cursor
# ---------------------------------------------------------------------- #


def _plain(value: Any) -> Any:
    """Converte instâncias de Decimal do boto3 para tipos nativos (int/float).

    Args:
        value (Any): Valor a ser convertido.

    Returns:
        Any: Valor com Decimals convertidos em int ou float.
    """
    if isinstance(value, Decimal):
        as_int = int(value)
        return as_int if value == as_int else float(value)
    if isinstance(value, dict):
        return {key: _plain(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(inner) for inner in value]
    if isinstance(value, set):
        return sorted(_plain(inner) for inner in value)
    return value


def _text(value: Any) -> str | None:
    """Converte um valor para string sem espaços nas extremidades ou None.

    Args:
        value (Any): Valor original.

    Returns:
        str | None: String tratada ou None se vazia.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_datetime(value: Any) -> datetime:
    """Converte um valor de data/hora em datetime UTC.

    Args:
        value (Any): Valor bruto contendo timestamp.

    Returns:
        datetime: Objeto datetime normalizado em UTC ou o epoch base em caso de falha.
    """
    parsed = _parse_optional_datetime(value)
    if parsed is None:
        # Item sem timestamp nao deveria existir (o worker exige), mas a API de
        # leitura nao pode quebrar por causa de um item corrompido.
        return datetime.fromtimestamp(0, UTC)
    return parsed


def _parse_optional_datetime(value: Any) -> datetime | None:
    """Converte opcionalmente uma string de data/hora para datetime UTC.

    Args:
        value (Any): Valor opcional.

    Returns:
        datetime | None: Objeto datetime em UTC ou None.
    """
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _key_of(item: dict[str, Any], index: str | None) -> dict[str, Any]:
    """A chave que o ExclusiveStartKey precisa, por indice consultado.

    Args:
        item (dict[str, Any]): Item bruto do DynamoDB.
        index (str | None): Nome do índice.

    Returns:
        dict[str, Any]: Chaves do item para controle de paginação.
    """
    key = {"pk": item.get("pk"), "sk": item.get("sk")}
    if index == "gsi1":
        key |= {"gsi1pk": item.get("gsi1pk"), "gsi1sk": item.get("gsi1sk")}
    elif index == "gsi2":
        key |= {"gsi2pk": item.get("gsi2pk"), "gsi2sk": item.get("gsi2sk")}
    return {name: value for name, value in key.items() if value is not None}


def _encode_cursor(state: dict[str, Any]) -> str:
    """Codifica o estado da paginação em uma string base64 segura para URL.

    Args:
        state (dict[str, Any]): Dicionário com o estado das partições ou offset.

    Returns:
        str: String codificada em Base64 URL safe.
    """
    raw = json.dumps(state, default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str | None) -> dict[str, Any]:
    """Decodifica a string de cursor em um dicionário de estado.

    Args:
        cursor (str | None): Cursor Base64 recebido do cliente.

    Returns:
        dict[str, Any]: Dicionário com o estado decodificado.

    Raises:
        ValidationError: Se o cursor for malformado ou inválido.
    """
    if not cursor:
        return {}
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception as error:
        # ValidationError e nao ValueError: cursor corrompido e erro do cliente
        # (422), nao falha interna. Sem isso vira 500 e some no log.
        raise ValidationError("cursor invalido ou expirado", field="cursor") from error
    if not isinstance(decoded, dict):
        raise ValidationError("cursor invalido ou expirado", field="cursor")
    return decoded


def build_repository(
    table_name: str,
    *,
    region: str,
    endpoint_url: str | None = None,
    gsi1_shards: int = 10,
    user_id_hash_salt: str = "",
    max_workers: int = 16,
) -> DynamoEventRepository:
    """Cria e configura uma instância de DynamoEventRepository com pool de conexões otimizado.

    Args:
        table_name (str): Nome da tabela no AWS DynamoDB.
        region (str): Região da AWS.
        endpoint_url (str | None, optional): URL customizada do DynamoDB (para testes locais).
        gsi1_shards (int, optional): Quantidade de shards na GSI1. Padrão é 10.
        user_id_hash_salt (str, optional): Sal para desidentificação de usuário.
        max_workers (int, optional): Número máximo de conexões paralelas. Padrão é 16.

    Returns:
        DynamoEventRepository: Instância pronta do repositório.
    """
    import boto3
    from botocore.config import Config as BotoConfig

    # O pool precisa comportar o fan-out paralelo; com o default (10) as
    # threads excedentes ficariam em fila esperando conexao, anulando o ganho.
    boto_config = BotoConfig(
        region_name=region,
        retries={"max_attempts": 3, "mode": "standard"},
        max_pool_connections=max_workers + 4,
        connect_timeout=3,
        read_timeout=10,
    )

    def make_table():
        """Cria um recurso de Table novo, um por thread do fan-out.

        Returns:
            Any: Recurso `dynamodb.Table` do boto3, que não é thread-safe e por
                isso não pode ser compartilhado entre as queries paralelas.
        """
        resource = boto3.resource(
            "dynamodb",
            config=boto_config,
            **({"endpoint_url": endpoint_url} if endpoint_url else {}),
        )
        return resource.Table(table_name)

    return DynamoEventRepository(
        make_table(),
        gsi1_shards=gsi1_shards,
        user_id_hash_salt=user_id_hash_salt,
        max_workers=max_workers,
        table_factory=make_table,
    )
