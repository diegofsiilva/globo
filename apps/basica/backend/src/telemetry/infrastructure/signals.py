"""Leitura para os sinais de desvio ativo (tela Agora, v1 simplificada).

O motor de hipoteses de verdade (deteccao EWMA causal com
`gold.circadian_state`, qualidade de fonte, correlacao, etc -- ver
`processing/README.md`) esta sendo implementado por outro integrante do time
na branch `feat/hipotese`. Este modulo NAO e esse motor: e uma leitura
independente, so para a rota `GET /api/v1/signals`, que calcula o desvio
estatistico direto de `gold.v_feature_bucket` a cada requisicao, sem estado
persistido nem dependencia do trabalho do motor.

Baseline: media e desvio-padrao por (source, entity, metric, hora_brt) numa
janela anterior a `desde`. E uma aproximacao do que `gold.circadian_state`
faria de forma incremental -- essa tabela existe mas nenhum job a popula
ainda. Cada chamada recalcula do zero; nao ha cache.

Como no restante da API, toda consulta aponta para uma view `v_*` (GRANT de
`argus_reader`, ver 001_schemas_e_extensoes.sql). Nenhuma tabela nova foi
criada para esta versao simplificada.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)


class SignalsRepository:
    """Le desvios de `gold.v_feature_bucket` e sessoes de `silver.v_session_event`."""

    def __init__(self, pool: ConnectionPool, *, baseline_hours: int = 168) -> None:
        """Inicializa o repositorio.

        Args:
            pool (ConnectionPool): Pool de conexao ja aberto.
            baseline_hours (int): Quanto tempo antes de `desde` olhar para
                calcular media/desvio por hora do dia. Padrao de 7 dias (168h)
                garante ao menos algumas amostras por `hora_brt` mesmo em
                fontes com bucket de 15 min.
        """
        self._pool = pool
        self._baseline_horas = baseline_hours

    def desvios(self, desde: datetime, ate: datetime) -> list[dict[str, Any]]:
        """Compara cada bucket da janela com a media/desvio da mesma hora do
        dia numa janela anterior.

        Args:
            desde (datetime): Inicio da janela analisada.
            ate (datetime): Fim da janela analisada.

        Returns:
            list[dict[str, Any]]: Uma linha por bucket, com `z` calculado.
                `z` vem `None` quando a fonte nao tem historico suficiente
                (menos de 3 amostras) na janela de base.
        """
        baseline_desde = desde - timedelta(hours=self._baseline_horas)
        return self._all(
            sql.SQL(
                """
                WITH janela AS (
                  SELECT bucket_ts, source, entity, metric, value, hora_brt
                    FROM gold.v_feature_bucket
                   WHERE bucket_ts >= %s AND bucket_ts <= %s
                     AND value IS NOT NULL
                ),
                base AS (
                  SELECT source, entity, metric, hora_brt,
                         avg(value)         AS media,
                         stddev_samp(value) AS desvio,
                         count(*)           AS n
                    FROM gold.v_feature_bucket
                   WHERE bucket_ts >= %s AND bucket_ts < %s
                     AND value IS NOT NULL
                   GROUP BY source, entity, metric, hora_brt
                )
                SELECT j.bucket_ts, j.source, j.entity, j.metric, j.value,
                       b.media, b.desvio, b.n,
                       CASE
                         WHEN b.desvio IS NULL OR b.desvio = 0 OR b.n < 3 THEN NULL
                         ELSE (j.value - b.media) / b.desvio
                       END AS z
                  FROM janela j
                  LEFT JOIN base b
                    ON b.source = j.source AND b.entity = j.entity
                   AND b.metric = j.metric AND b.hora_brt = j.hora_brt
                 ORDER BY j.source, j.entity, j.metric, j.bucket_ts
                """
            ),
            [desde, ate, baseline_desde, desde],
        )

    def contagem_sessoes(self, desde: datetime, ate: datetime) -> int:
        """Sessoes distintas na janela, direto de `silver.v_session_event`.

        Args:
            desde (datetime): Inicio da janela.
            ate (datetime): Fim da janela.

        Returns:
            int: Quantidade de `session_id` distintos.
        """
        linha = self._one(
            sql.SQL(
                """
                SELECT count(DISTINCT session_id) AS n
                  FROM silver.v_session_event
                 WHERE ts >= %s AND ts <= %s
                """
            ),
            [desde, ate],
        )
        return int(linha["n"]) if linha else 0

    def _all(self, instrucao, params: list[Any]) -> list[dict[str, Any]]:
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(instrucao, params)
            return cur.fetchall()

    def _one(self, instrucao, params: list[Any]) -> dict[str, Any] | None:
        linhas = self._all(instrucao, params)
        return linhas[0] if linhas else None
