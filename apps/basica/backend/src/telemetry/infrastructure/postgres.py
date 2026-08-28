"""Adaptador de leitura em PostgreSQL. Substitui o de DynamoDB da v2.

A troca nao e so de banco. Tres coisas mudam de natureza:

  Autorizacao
      Na v2 era IAM: a Lambda tinha `dynamodb:Query` na tabela. Agora e GRANT:
      a Lambda entra como `argus_api`, que so tem SELECT nas views `v_*`. A
      diferenca pratica e que o IAM nao sabe filtrar LINHA por `available_at`, e
      a view sabe -- a barreira contra vazamento de futuro passou a ser do
      banco, e nao da aplicacao.

  Agregacao
      Na v2, `breakdown` e `timeseries` liam ate MAX_ITEMS_SCANNED itens e
      agregavam em Python, porque o DynamoDB nao tem GROUP BY. Aqui a agregacao
      e do banco, sobre o conjunto inteiro. O teto vira LIMIT no resultado, e
      nao no que foi lido -- some a diferenca entre "top 20" e "top 20 dos
      primeiros 20 mil".

  Estrategia de indice
      Some o fan-out da GSI1 sharded, que existia so para contornar o teto de
      1000 WCU por particao do DynamoDB. `QueryStats.strategy` continua na
      resposta, agora dizendo qual indice o PostgreSQL usou.

TODA consulta aqui aponta para uma view `v_*`. Nenhuma toca tabela base -- e
nao adiantaria tentar: o GRANT recusaria.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from telemetry.application.redaction import redact_attributes
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

# Colunas do envelope que aceitam filtro direto. Lista fechada: o nome vai para
# dentro da instrucao como IDENTIFICADOR, e identificador nao pode ser bind.
# Sem esta lista, `?dimension=` viraria injecao de SQL.
COLUNAS_FILTRAVEIS = frozenset(
    {
        "session_id",
        "device_id",
        "event_name",
        "app_env",
        "app_target",
        "app_version",
        "app_bucket",
        "device_os",
        "device_manufacturer",
        "device_model",
        "route_path",
        "uf",
        "isp",
    }
)

# Dimensoes validas para breakdown e facets. E a mesma lista, sem os campos de
# alta cardinalidade: agrupar por session_id devolveria uma linha por sessao, o
# que nao e um agrupamento, e um dump.
COLUNAS_AGRUPAVEIS = COLUNAS_FILTRAVEIS - {"session_id", "device_id"}


class PostgresEventRepository:
    """Le eventos de sessao da view `silver.v_session_event`."""

    def __init__(
        self,
        pool: ConnectionPool,
        *,
        user_id_hash_salt: str,
        default_window_hours: int = 168,
        max_items_scanned: int = 20_000,
    ) -> None:
        """Inicializa o repositorio.

        Args:
            pool (ConnectionPool): Pool de conexao ja aberto.
            user_id_hash_salt (str): Salt do hash de user_id na saida (RNF10).
            default_window_hours (int): Janela assumida quando a consulta nao
                informa periodo. Evita varrer a tabela inteira sem querer.
            max_items_scanned (int): Teto de linhas devolvidas numa busca.
        """
        self._pool = pool
        self._salt = user_id_hash_salt
        self._janela = default_window_hours
        self._teto = max_items_scanned

    # ----------------------------------------------------------------- #
    # Busca
    # ----------------------------------------------------------------- #

    def search(self, filters: EventFilters) -> EventPage:
        """Busca eventos aplicando os filtros cumulativos.

        Args:
            filters (EventFilters): Filtros e paginacao.

        Returns:
            EventPage: Pagina de eventos, com cursor e estatisticas.
        """
        onde, params = self._where(filters)

        # Paginacao por keyset e nao por OFFSET. Com OFFSET, a pagina 50 obriga
        # o banco a ler e descartar as 49 anteriores; o custo cresce conforme se
        # avanca. Com keyset o custo e constante -- e o cursor continua valido
        # mesmo se linhas novas entrarem no meio.
        cursor = _decode_cursor(filters.cursor)
        if cursor:
            onde.append(sql.SQL("(ts, event_id) < (%s, %s)"))
            params.extend([cursor["ts"], cursor["event_id"]])

        limite = max(1, min(filters.limit, self._teto))
        instrucao = sql.SQL(
            """
            SELECT * FROM silver.v_session_event
             WHERE {onde}
             ORDER BY ts DESC, event_id DESC
             LIMIT %s
            """
        ).format(onde=sql.SQL(" AND ").join(onde))

        # Pede uma linha a mais que o pedido: e assim que se sabe se ha proxima
        # pagina sem pagar um COUNT(*) sobre o conjunto inteiro.
        linhas = self._query(instrucao, [*params, limite + 1])

        tem_mais = len(linhas) > limite
        linhas = linhas[:limite]

        proximo = None
        if tem_mais and linhas:
            ultima = linhas[-1]
            proximo = _encode_cursor(ultima["ts"], ultima["event_id"])

        return EventPage(
            items=[self._to_event(linha) for linha in linhas],
            next_cursor=proximo,
            stats=QueryStats(
                strategy=self._estrategia(filters),
                queries=1,
                # No PostgreSQL nao ha diferenca entre lido e devolvido do ponto
                # de vista da conta: o filtro roda no banco, sobre o indice.
                scanned=len(linhas),
                returned=len(linhas),
            ),
        )

    def get(self, session_id: str, event_id: str) -> TelemetryEvent | None:
        """Busca um evento pela sessao e pelo id.

        Args:
            session_id (str): Sessao a que o evento pertence.
            event_id (str): Identificador do evento.

        Returns:
            TelemetryEvent | None: O evento, ou None se nao existir (ou se o
                relogio virtual ainda nao o alcancou).
        """
        linhas = self._query(
            sql.SQL(
                """
                SELECT * FROM silver.v_session_event
                 WHERE session_id = %s AND event_id = %s
                 LIMIT 1
                """
            ),
            [session_id, event_id],
        )
        return self._to_event(linhas[0]) if linhas else None

    # ----------------------------------------------------------------- #
    # Agregacoes
    # ----------------------------------------------------------------- #

    def breakdown(
        self, filters: EventFilters, dimension: str, limit: int = 20
    ) -> Sequence[EventMetric]:
        """Agrupa os eventos por uma dimensao.

        Args:
            filters (EventFilters): Filtros aplicados antes do agrupamento.
            dimension (str): Coluna de agrupamento.
            limit (int): Quantas categorias devolver.

        Returns:
            Sequence[EventMetric]: Categorias, da mais frequente para a menos.

        Raises:
            ValueError: Se a dimensao nao estiver na lista permitida.
        """
        coluna = self._coluna_agrupavel(dimension)
        onde, params = self._where(filters)

        linhas = self._query(
            sql.SQL(
                """
                SELECT COALESCE({coluna}, '(sem valor)') AS chave,
                       count(*) AS total,
                       avg(duration) FILTER (WHERE duration IS NOT NULL) AS media
                  FROM silver.v_session_event
                 WHERE {onde}
                 GROUP BY 1
                 ORDER BY total DESC, chave
                 LIMIT %s
                """
            ).format(coluna=coluna, onde=sql.SQL(" AND ").join(onde)),
            [*params, limit],
        )

        return [
            EventMetric(
                key=linha["chave"],
                count=int(linha["total"]),
                # `duration` vem em SEGUNDOS, como o app envia; o dashboard usa
                # milissegundos. A conversao mora aqui, na saida, e nao na
                # ingestao -- a bronze guarda o que a origem mandou.
                average_duration_ms=(
                    round(float(linha["media"]) * 1000, 2) if linha["media"] is not None else None
                ),
            )
            for linha in linhas
        ]

    def crosstab(
        self, filters: EventFilters, dimension_x: str, dimension_y: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Agrupa eventos por DUAS dimensoes (heatmap do Recorte, RF16).

        `breakdown` agrupa por uma dimensao so; o heatmap dispositivo x
        regiao (ou qualquer outro par) precisa das duas contagens ao mesmo
        tempo, que uma dimensao unica nao responde.

        Args:
            filters (EventFilters): Filtros aplicados antes do agrupamento.
            dimension_x (str): Coluna do primeiro eixo.
            dimension_y (str): Coluna do segundo eixo.
            limit (int): Teto de celulas devolvidas.

        Returns:
            list[dict[str, Any]]: Uma linha por combinacao (x, y) com `count`,
                da mais frequente para a menos.

        Raises:
            ValueError: Se alguma das duas dimensoes nao for agrupavel.
        """
        coluna_x = self._coluna_agrupavel(dimension_x)
        coluna_y = self._coluna_agrupavel(dimension_y)
        onde, params = self._where(filters)

        linhas = self._query(
            sql.SQL(
                """
                SELECT COALESCE({x}, '(sem valor)') AS chave_x,
                       COALESCE({y}, '(sem valor)') AS chave_y,
                       count(*) AS total
                  FROM silver.v_session_event
                 WHERE {onde}
                 GROUP BY 1, 2
                 ORDER BY total DESC
                 LIMIT %s
                """
            ).format(x=coluna_x, y=coluna_y, onde=sql.SQL(" AND ").join(onde)),
            [*params, limit],
        )
        return [
            {"x": linha["chave_x"], "y": linha["chave_y"], "count": int(linha["total"])}
            for linha in linhas
        ]

    def timeseries(self, filters: EventFilters, interval_minutes: int = 60) -> Sequence[TimeBucket]:
        """Agrupa os eventos numa serie temporal.

        Args:
            filters (EventFilters): Filtros aplicados.
            interval_minutes (int): Largura do bucket, em minutos.

        Returns:
            Sequence[TimeBucket]: Buckets em ordem cronologica.
        """
        onde, params = self._where(filters)
        intervalo = timedelta(minutes=max(1, interval_minutes))

        # `date_bin` alinha os buckets a uma origem FIXA, e nao ao primeiro
        # evento encontrado. Sem isso, duas consultas com filtros diferentes
        # devolveriam buckets deslocados entre si e os graficos nao se
        # sobreporiam na tela Comparar.
        linhas = self._query(
            sql.SQL(
                """
                SELECT date_bin(%s, ts, timestamptz '2026-01-01') AS bucket,
                       event_name,
                       count(*) AS total
                  FROM silver.v_session_event
                 WHERE {onde}
                 GROUP BY 1, 2
                 ORDER BY 1
                """
            ).format(onde=sql.SQL(" AND ").join(onde)),
            [intervalo, *params],
        )

        buckets: dict[datetime, TimeBucket] = {}
        for linha in linhas:
            momento = linha["bucket"]
            atual = buckets.get(momento)
            if atual is None:
                atual = TimeBucket(bucket=momento, count=0, by_event_name={})
                buckets[momento] = atual
            total = int(linha["total"])
            atual.by_event_name[linha["event_name"]] = total
            buckets[momento] = TimeBucket(
                bucket=momento,
                count=atual.count + total,
                by_event_name=atual.by_event_name,
            )

        return sorted(buckets.values(), key=lambda b: b.bucket)

    def facets(self, fields: Sequence[str], limit: int = 20) -> dict[str, list[str]]:
        """Lista os valores distintos de cada campo, para montar os filtros.

        Args:
            fields (Sequence[str]): Campos pedidos.
            limit (int): Teto de valores por campo.

        Returns:
            dict[str, list[str]]: Valores por campo.

        Raises:
            ValueError: Se algum campo nao for agrupavel.
        """
        for campo in fields:
            self._coluna_agrupavel(campo)
        if not fields:
            return {}

        # Um scan so, recortado na mesma janela padrao das outras leituras.
        # A versao anterior fazia um GROUP BY sem recorte por campo -- N
        # varreduras da particao inteira, e oferecia valores que sumiram ha
        # semanas.
        pares = sql.SQL(", ").join(
            sql.SQL("({rotulo}, {coluna}::text)").format(
                rotulo=sql.Literal(campo), coluna=sql.Identifier(campo)
            )
            for campo in fields
        )
        linhas = self._query(
            sql.SQL(
                """
                WITH janela AS (
                  SELECT {colunas}
                    FROM silver.v_session_event
                   WHERE ts >= sim.now() - %s
                ),
                contagem AS (
                  SELECT d.campo, d.valor, count(*) AS total
                    FROM janela
                    CROSS JOIN LATERAL (VALUES {pares}) AS d(campo, valor)
                   WHERE d.valor IS NOT NULL
                   GROUP BY d.campo, d.valor
                ),
                ranqueado AS (
                  SELECT campo, valor,
                         row_number() OVER (
                           PARTITION BY campo ORDER BY total DESC, valor
                         ) AS posicao
                    FROM contagem
                )
                SELECT campo, valor
                  FROM ranqueado
                 WHERE posicao <= %s
                 ORDER BY campo, posicao
                """
            ).format(
                colunas=sql.SQL(", ").join(sql.Identifier(c) for c in fields),
                pares=pares,
            ),
            [timedelta(hours=self._janela), limit],
        )
        resultado: dict[str, list[str]] = {campo: [] for campo in fields}
        for linha in linhas:
            resultado[linha["campo"]].append(linha["valor"])
        return resultado

    def ping(self) -> bool:
        """Verifica se o banco responde e se a view esta acessivel.

        Consulta a view, e nao `SELECT 1`: o que interessa saber e se o GRANT
        continua de pe e se a migration foi aplicada, nao apenas se o TCP abriu.

        Returns:
            bool: True se a leitura funcionou.
        """
        try:
            self._query(sql.SQL("SELECT 1 FROM silver.v_session_event LIMIT 1"), [])
        except Exception:
            log.warning("readiness: a view de eventos nao respondeu", exc_info=True)
            return False
        return True

    # ----------------------------------------------------------------- #
    # Internos
    # ----------------------------------------------------------------- #

    def _query(self, instrucao, params: list[Any]) -> list[dict]:
        """Executa uma consulta e devolve as linhas como dicionario.

        Args:
            instrucao: Instrucao ja composta por psycopg.sql.
            params (list[Any]): Parametros de bind.

        Returns:
            list[dict]: Linhas retornadas.
        """
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(instrucao, params)
            return cur.fetchall()

    def _where(self, filters: EventFilters) -> tuple[list, list[Any]]:
        """Monta as condicoes do WHERE a partir dos filtros.

        Args:
            filters (EventFilters): Filtros da consulta.

        Returns:
            tuple[list, list[Any]]: Condicoes e parametros de bind.
        """
        onde = [sql.SQL("TRUE")]
        params: list[Any] = []

        for campo in COLUNAS_FILTRAVEIS:
            valor = getattr(filters, campo, None)
            if valor:
                onde.append(sql.SQL("{} = %s").format(sql.Identifier(campo)))
                params.append(valor)

        de = filters.occurred_from
        ate = filters.occurred_to
        if de is None and ate is None:
            # Sem periodo informado, assume a janela padrao terminando em
            # `sim.now()` -- o presente VIRTUAL, e nao o relogio de parede.
            # Usar now() aqui faria a tela vir vazia sempre que o simulador
            # estivesse replicando uma janela do passado.
            onde.append(sql.SQL("ts >= sim.now() - %s"))
            params.append(timedelta(hours=self._janela))
        else:
            if de is not None:
                onde.append(sql.SQL("ts >= %s"))
                params.append(de)
            if ate is not None:
                onde.append(sql.SQL("ts <= %s"))
                params.append(ate)

        return onde, params

    def _coluna_agrupavel(self, nome: str):
        """Valida a dimensao e devolve o identificador escapado.

        Args:
            nome (str): Nome pedido pela consulta.

        Returns:
            psycopg.sql.Identifier: Identificador seguro.

        Raises:
            ValueError: Se o nome nao estiver na lista permitida.
        """
        if nome not in COLUNAS_AGRUPAVEIS:
            raise ValueError(
                f"dimensao '{nome}' nao e agrupavel. "
                f"Validas: {', '.join(sorted(COLUNAS_AGRUPAVEIS))}"
            )
        return sql.Identifier(nome)

    def _estrategia(self, filters: EventFilters) -> str:
        """Descreve qual indice deve responder a consulta.

        Vai na resposta pelo mesmo motivo que ia na v2: deixar visivel quando
        uma tela esta cara. Aqui a diferenca nao e mais de custo por item lido,
        e sim entre usar indice e varrer particao.

        Args:
            filters (EventFilters): Filtros da consulta.

        Returns:
            str: Nome da estrategia.
        """
        if filters.session_id:
            return "indice_sessao"
        if filters.device_id:
            return "indice_aparelho"
        if filters.event_name:
            return "indice_tipo_e_tempo"
        return "particao_por_tempo"

    def _to_event(self, linha: dict) -> TelemetryEvent:
        """Converte uma linha da view na entidade de dominio.

        Args:
            linha (dict): Linha da view.

        Returns:
            TelemetryEvent: Entidade de dominio.
        """
        # A redacao acontece na LEITURA, e nao na ingestao: a bronze guarda o
        # que a origem mandou (e um `authorization` no header de request e o
        # que a origem manda). Quem nao pode ver isso e quem consome a API.
        #
        # `redact_attributes` derruba `response_headers`, filtra
        # `request_headers` por allowlist e tira credencial da query string do
        # `request_url`. Sem esta linha, o token de autorizacao de cada
        # requisicao das TVs sairia no JSON do dashboard.
        payload = redact_attributes(dict(linha.get("payload") or {}))

        # Campos que a entidade promove a atributo de primeira classe saem do
        # payload para nao aparecerem duas vezes na resposta.
        clock_skew = bool(payload.pop("clock_skew", False))
        action = payload.pop("action", None)
        app_resolution = payload.pop("app_resolution", None)
        device_resolution = payload.pop("device_resolution", None)
        # A coluna guarda o ano quando ele e numerico; o payload guarda o texto
        # original quando nao e ("unknown" e valor real do parque). A entidade
        # aceita os dois, entao a saida da API nao perde nenhum dos casos.
        ano_texto = payload.pop("device_model_year", None)
        device_model_year = ano_texto if ano_texto is not None else linha.get("device_model_year")
        device_os_version = payload.pop("device_os_version", None)

        # `duration` vem em segundos e o dashboard usa milissegundos.
        duracao = linha.get("duration")

        return TelemetryEvent(
            event_id=linha["event_id"],
            event_name=linha["event_name"],
            occurred_at=linha["ts"],
            session_id=linha["session_id"],
            device_id=linha.get("device_id") or "",
            ingested_at=None,
            duration_ms=round(float(duracao) * 1000, 3) if duracao is not None else None,
            action=action,
            route_path=linha.get("route_path"),
            app_bucket=linha.get("app_bucket"),
            app_env=linha.get("app_env"),
            app_target=linha.get("app_target"),
            app_version=linha.get("app_version"),
            app_resolution=app_resolution,
            device_manufacturer=linha.get("device_manufacturer"),
            device_model=linha.get("device_model"),
            device_model_year=device_model_year,
            device_os=linha.get("device_os"),
            device_os_version=device_os_version,
            device_resolution=device_resolution,
            user_id_hash=self._hash_user(linha.get("user_id")),
            clock_skew=clock_skew,
            attributes=payload,
        )

    def _hash_user(self, user_id: str | None) -> str | None:
        """Aplica o hash com salt no identificador do usuario (RNF10).

        O banco guarda o identificador original porque a ingestao nao o
        transforma; o hash acontece na LEITURA. Trocar o salt reembaralha tudo:
        eventos do mesmo usuario deixam de agrupar com os antigos.

        Args:
            user_id (str | None): Identificador cru.

        Returns:
            str | None: Hash de 16 caracteres, ou None.
        """
        if not user_id:
            return None
        digest = hashlib.sha256(f"{self._salt}{user_id}".encode())
        return digest.hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Cursor
# --------------------------------------------------------------------------- #


def _encode_cursor(ts: datetime, event_id: str) -> str:
    """Serializa a posicao da paginacao num token opaco.

    Opaco de proposito: o formato e detalhe de implementacao, e um cliente que
    montasse cursor a mao ficaria preso a ele.

    Args:
        ts (datetime): Timestamp da ultima linha da pagina.
        event_id (str): Id da ultima linha da pagina.

    Returns:
        str: Token em base64 url-safe.
    """
    bruto = json.dumps({"ts": ts.isoformat(), "event_id": event_id})
    return base64.urlsafe_b64encode(bruto.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> dict | None:
    """Le o token de paginacao.

    Cursor invalido e ERRO DO CLIENTE (422), e nao um 500 nem um silencioso
    "volta para a primeira pagina".

    Devolver a primeira pagina esconderia um defeito do cliente do pior jeito
    possivel: um laco de paginacao que corrompesse o token receberia a pagina 1
    de volta, acharia que ha mais dado, e giraria para sempre lendo o mesmo
    trecho. Melhor falhar na cara.

    Args:
        cursor (str | None): Token recebido.

    Returns:
        dict | None: Posicao decodificada, ou None se nao havia cursor.

    Raises:
        ValidationError: Se o token nao for decodificavel.
    """
    if not cursor:
        return None
    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        dados = json.loads(base64.urlsafe_b64decode(preenchido))
        return {
            "ts": datetime.fromisoformat(dados["ts"]),
            "event_id": dados["event_id"],
        }
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValidationError(
            "cursor invalido: use o `next_cursor` da resposta anterior",
            field="cursor",
        ) from exc


# --------------------------------------------------------------------------- #
# Construcao
# --------------------------------------------------------------------------- #


def build_pool(database_url: str, *, min_size: int = 0, max_size: int = 2) -> ConnectionPool:
    """Abre o pool de conexao da Lambda.

    `min_size=0` e proposital, e e o oposto do que se faz num worker: uma Lambda
    ociosa e congelada, e uma conexao mantida aberta durante o congelamento
    ocupa um slot no RDS sem que ninguem do outro lado possa usa-la. Com 0, a
    conexao nasce na primeira consulta.

    `max_size=2` porque cada execucao concorrente da Lambda e um PROCESSO
    proprio com o proprio pool -- a concorrencia real e o numero de Lambdas
    simultaneas multiplicado por isto, e o teto do db.t3.medium e ~340.

    Args:
        database_url (str): DSN de conexao.
        min_size (int): Conexoes ociosas mantidas.
        max_size (int): Teto de conexoes por processo.

    Returns:
        ConnectionPool: Pool aberto.
    """
    return ConnectionPool(
        conninfo=database_url,
        min_size=min_size,
        max_size=max_size,
        open=True,
        # A Lambda tem timeout proprio; esperar mais que isso por uma conexao so
        # garante que a resposta vai ser um 502 em vez de um erro legivel.
        timeout=10,
        kwargs={
            "application_name": "argus-read-api",
            "autocommit": True,
            # JIT em CTE de 4,9 M linhas adiciona segundos no PRIMEIRO plano
            # (o caso da Lambda fria). work_mem maior evita hash/sort spilling
            # para disco no t3.medium. statement_timeout abaixo dos 30 s da
            # Lambda devolve 500 legivel em vez de 502 do API Gateway.
            "options": "-c jit=off -c statement_timeout=15000 -c work_mem=64MB",
        },
        check=ConnectionPool.check_connection,
    )


def build_repository(
    database_url: str,
    *,
    user_id_hash_salt: str,
    default_window_hours: int = 168,
    max_items_scanned: int = 20_000,
) -> PostgresEventRepository:
    """Monta o repositorio de leitura.

    Args:
        database_url (str): DSN de conexao.
        user_id_hash_salt (str): Salt do hash de user_id.
        default_window_hours (int): Janela padrao das consultas sem periodo.
        max_items_scanned (int): Teto de linhas por busca.

    Returns:
        PostgresEventRepository: Repositorio pronto.
    """
    return PostgresEventRepository(
        build_pool(database_url),
        user_id_hash_salt=user_id_hash_salt,
        default_window_hours=default_window_hours,
        max_items_scanned=max_items_scanned,
    )


__all__ = [
    "PostgresEventRepository",
    "build_pool",
    "build_repository",
    "UTC",
]
