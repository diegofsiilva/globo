"""Repositorio das views publicas de hipoteses e da funcao estreita de feedback."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from telemetry.domain.exceptions import ConflictError


def _encode_cursor(row: dict[str, Any]) -> str:
    """Empacota a posição da última linha lida num cursor opaco.

    Paginação keyset, e não `OFFSET`: com `OFFSET` o banco varre e descarta as
    páginas anteriores a cada requisição, e uma hipótese gerada no intervalo
    entre duas páginas empurraria uma linha para fora da leitura sem que o
    cliente percebesse.

    Args:
        row (dict[str, Any]): Última linha da página, com `score`,
            `effect_start` e `hypothesis_id` -- exatamente as três colunas do
            `ORDER BY`.

    Returns:
        str: Base64 URL-safe sem preenchimento. Opaco de propósito: o cliente
            não deve construir cursor à mão, e o formato pode mudar.
    """
    payload = json.dumps(
        [row["score"], row["effect_start"].isoformat(), row["hypothesis_id"]],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[float, datetime, int]:
    """Desempacota um cursor produzido por `_encode_cursor`.

    Args:
        value (str): Cursor recebido na query string.

    Returns:
        tuple[float, datetime, int]: Score, início do efeito e id da hipótese.

    Raises:
        ValueError: Se o cursor não decodificar. Quem chama o converte em 422 --
            devolver a primeira página em silêncio faria o cliente paginar em
            círculo sem nunca perceber.
    """
    try:
        padded = value + "=" * (-len(value) % 4)
        score, effect_start, hypothesis_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        return float(score), datetime.fromisoformat(effect_start), int(hypothesis_id)
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as error:
        raise ValueError("cursor invalido") from error


class HypothesisRepository:
    """Le hipoteses geradas e registra o feedback do operador.

    Como todo adaptador desta API, so enxerga views `v_*` -- `argus_reader` nao
    tem `SELECT` em tabela base. A unica excecao e o feedback, que chama a
    funcao `SECURITY DEFINER` `gold.submit_hypothesis_feedback`: a escrita
    precisa de privilegio que o usuario de leitura nao tem, e concentra-la numa
    funcao e o que evita conceder `INSERT` a API inteira.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        """Inicializa o repositorio.

        Args:
            pool (ConnectionPool): Pool ja aberto, compartilhado com os demais
                adaptadores -- ver a nota sobre pool unico em `app.create_app`.
        """
        self._pool = pool

    def runs(self, *, limit: int = 50, before_run_id: int | None = None) -> list[dict]:
        """Lista as execucoes concluidas do motor, da mais recente para a mais antiga.

        Args:
            limit (int): Quantas execucoes devolver.
            before_run_id (int | None): Devolve apenas execucoes anteriores a
                este id. E a paginacao desta rota: `run_id` e monotonico, entao
                serve de cursor sem precisar de um opaco.

        Returns:
            list[dict]: Uma linha por execucao concluida.
        """
        where = sql.SQL("TRUE")
        params: list[Any] = []
        if before_run_id is not None:
            where = sql.SQL("run_id < %s")
            params.append(before_run_id)
        return self._all(
            sql.SQL(
                """
                SELECT * FROM gold.v_hypothesis_run
                 WHERE {where}
                 ORDER BY run_id DESC
                 LIMIT %s
                """
            ).format(where=where),
            [*params, limit],
        )

    def list(
        self,
        *,
        family: str | None = None,
        kind: str | None = None,
        confidence: str | None = None,
        review_status: str | None = None,
        source: str | None = None,
        entity: str | None = None,
        run_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Pagina as hipoteses geradas, das mais fortes para as mais fracas.

        Todos os filtros sao cumulativos e opcionais; nenhum informado devolve
        a janela inteira. A ordenacao e por `score` decrescente, com
        `effect_start` e `hypothesis_id` como desempate -- os tres juntos formam
        a chave do cursor keyset.

        Args:
            family (str | None): Familia da hipotese (uma das 11).
            kind (str | None): Tipo dentro da familia.
            confidence (str | None): Faixa de confianca declarada pelo motor.
            review_status (str | None): Situacao da revisao humana.
            source (str | None): Fonte da evidencia principal.
            entity (str | None): Entidade afetada.
            run_id (int | None): Restringe a uma execucao do motor.
            since (datetime | None): Efeito comecando a partir deste instante.
            until (datetime | None): Efeito comecando ate este instante.
            cursor (str | None): Cursor opaco da pagina anterior.
            limit (int): Tamanho da pagina.

        Returns:
            dict[str, Any]: `{"count", "items", "next_cursor"}`. Cada item ja
                traz `features` e `evidence` embutidos.

        Raises:
            ValueError: Se o cursor nao decodificar (vira 422 na camada HTTP).
        """
        clauses = [sql.SQL("TRUE")]
        params: list[Any] = []
        for column, value in (
            ("family", family),
            ("kind", kind),
            ("confidence", confidence),
            ("review_status", review_status),
            ("run_id", run_id),
        ):
            if value is not None:
                clauses.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
                params.append(value)
        if since is not None:
            clauses.append(sql.SQL("effect_start >= %s"))
            params.append(since)
        if until is not None:
            clauses.append(sql.SQL("effect_start <= %s"))
            params.append(until)
        if source is not None or entity is not None:
            evidence = [sql.SQL("e.hypothesis_id = h.hypothesis_id")]
            if source is not None:
                evidence.append(sql.SQL("e.source = %s"))
                params.append(source)
            if entity is not None:
                evidence.append(sql.SQL("e.entity = %s"))
                params.append(entity)
            clauses.append(
                sql.SQL("EXISTS (SELECT 1 FROM gold.v_hypothesis_evidence e WHERE {})").format(
                    sql.SQL(" AND ").join(evidence)
                )
            )
        if cursor:
            cursor_score, cursor_start, cursor_id = _decode_cursor(cursor)
            clauses.append(sql.SQL("(score, effect_start, hypothesis_id) < (%s, %s, %s)"))
            params.extend([cursor_score, cursor_start, cursor_id])

        rows = self._all(
            sql.SQL(
                """
                SELECT h.* FROM gold.v_hypothesis h
                 WHERE {where}
                 ORDER BY score DESC, effect_start DESC, hypothesis_id DESC
                 LIMIT %s
                """
            ).format(where=sql.SQL(" AND ").join(clauses)),
            [*params, limit + 1],
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        self._anexar_composicao(items)
        return {
            "items": items,
            "next_cursor": _encode_cursor(items[-1]) if has_more and items else None,
        }

    def _anexar_composicao(self, items: list[dict[str, Any]]) -> None:
        """Anexa `features` e `evidence` a cada item da pagina.

        A tela de Hipoteses desenha a decomposicao do score em TODOS os itens
        da lista (a faixa de contribuicao de cada fator), nao so no selecionado.
        Sem isto o front teria que pedir `/hypotheses/<id>` item a item -- N+1
        de invocacoes de Lambda a cada refetch. Aqui sao duas consultas por
        pagina, com `= ANY`, independente do tamanho dela.

        Args:
            items (list[dict[str, Any]]): Itens da pagina, alterados no lugar.
        """
        if not items:
            return
        ids = [item["hypothesis_id"] for item in items]

        # `features` ja vem agregado em jsonb por gold.v_hypothesis_detail
        # (022_hypothesis_views.sql). O usuario da API so tem GRANT nas views
        # `v_*`, entao a leitura passa por ela e nao por gold.hypothesis_feature.
        features = self._all(
            sql.SQL(
                "SELECT hypothesis_id, features FROM gold.v_hypothesis_detail "
                "WHERE hypothesis_id = ANY(%s)"
            ),
            [ids],
        )
        por_id = {linha["hypothesis_id"]: linha["features"] for linha in features}

        evidencias: dict[int, list[dict[str, Any]]] = {}
        for linha in self._all(
            sql.SQL(
                "SELECT * FROM gold.v_hypothesis_evidence WHERE hypothesis_id = ANY(%s) "
                "ORDER BY polarity, event_at, evidence_id"
            ),
            [ids],
        ):
            evidencias.setdefault(linha["hypothesis_id"], []).append(linha)

        for item in items:
            item["features"] = por_id.get(item["hypothesis_id"], [])
            item["evidence"] = evidencias.get(item["hypothesis_id"], [])

    def detail(self, hypothesis_id: int) -> dict[str, Any] | None:
        """Devolve uma hipotese com toda a sua evidencia.

        Args:
            hypothesis_id (int): Identificador da hipotese.

        Returns:
            dict[str, Any] | None: A hipotese com `evidence` ordenada por
                polaridade e instante, ou `None` se nao existir (vira 404).
        """
        row = self._one(
            "SELECT * FROM gold.v_hypothesis_detail WHERE hypothesis_id = %s",
            [hypothesis_id],
        )
        if row is None:
            return None
        row["evidence"] = self._all(
            """
            SELECT * FROM gold.v_hypothesis_evidence
             WHERE hypothesis_id = %s
             ORDER BY polarity, event_at, evidence_id
            """,
            [hypothesis_id],
        )
        return row

    def submit_feedback(
        self,
        *,
        hypothesis_id: int,
        verdict: str,
        note: str | None,
        reviewer_ref: str | None,
        idempotency_key: UUID,
        request_id: str | None,
    ) -> dict[str, Any] | None:
        """Registra o veredito do operador sobre uma hipotese, de forma idempotente.

        A idempotencia e do BANCO, e nao desta camada: `idempotency_key` e
        unica, e reenviar o mesmo par chave/payload devolve o registro ja
        gravado em vez de criar outro. E o que permite ao dashboard reenviar
        depois de um timeout sem duplicar a avaliacao.

        Args:
            hypothesis_id (int): Hipotese avaliada.
            verdict (str): Veredito do operador.
            note (str | None): Observacao livre, curta.
            reviewer_ref (str | None): Referencia de quem revisou.
            idempotency_key (UUID): Chave de deduplicacao, gerada pelo cliente.
            request_id (str | None): Correlacao com o log estruturado da API.

        Returns:
            dict[str, Any] | None: O feedback gravado, ou `None` quando a
                hipotese nao existe (`P0002` -> 404).

        Raises:
            ConflictError: Quando a mesma `idempotency_key` chega com um payload
                diferente (`P0003` -> 409). Aceitar em silencio sobrescreveria
                a avaliacao anterior sem que ninguem soubesse.
        """
        try:
            return self._one(
                """
                SELECT * FROM gold.submit_hypothesis_feedback(%s, %s, %s, %s, %s, %s)
                """,
                [hypothesis_id, verdict, note, reviewer_ref, idempotency_key, request_id],
            )
        except Exception as error:
            if getattr(error, "sqlstate", None) == "P0002":
                return None
            if getattr(error, "sqlstate", None) == "P0003":
                raise ConflictError("idempotency_key ja usada com outro payload") from error
            raise

    def _all(self, query, params: list[Any]) -> list[dict[str, Any]]:
        """Executa a consulta e devolve todas as linhas.

        Args:
            query: SQL cru ou ja composto por `psycopg.sql`.
            params (list[Any]): Parametros na ordem dos `%s`.

        Returns:
            list[dict[str, Any]]: Linhas como dicionarios.
        """
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def _one(self, query, params: list[Any]) -> dict[str, Any] | None:
        """Executa a consulta e devolve a primeira linha.

        Args:
            query: SQL cru ou ja composto por `psycopg.sql`.
            params (list[Any]): Parametros na ordem dos `%s`.

        Returns:
            dict[str, Any] | None: A primeira linha, ou `None` se nao houver.
        """
        rows = self._all(query, params)
        return rows[0] if rows else None
