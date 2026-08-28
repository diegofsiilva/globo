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

from datetime import datetime, timedelta
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

class SignalsRepository:
    """Le desvios ativos de ``gold.v_feature_bucket``."""

    def __init__(
        self,
        pool: ConnectionPool,
        *,
        baseline_hours: int = 168,
        max_active_series: int = 100,
    ) -> None:
        """Inicializa o repositorio.

        Args:
            pool (ConnectionPool): Pool de conexao ja aberto.
            baseline_hours (int): Quanto tempo antes de `desde` olhar para
                calcular media/desvio por hora do dia. Padrao de 7 dias (168h)
                garante ao menos algumas amostras por `hora_brt` mesmo em
                fontes com bucket de 15 min.
            max_active_series (int): Teto das series mais desviadas devolvidas.
                Evita transferir milhares de sparklines para uma tela que
                ordena os sinais por magnitude.
        """
        self._pool = pool
        self._baseline_horas = baseline_hours
        self._max_series_ativas = max_active_series

    def desvios(
        self, desde: datetime, ate: datetime, limiar: float = 2.0
    ) -> list[dict[str, Any]]:
        """Compara cada bucket da janela com a media/desvio da mesma hora do
        dia numa janela anterior.

        Args:
            desde (datetime): Inicio da janela analisada.
            ate (datetime): Fim da janela analisada.
            limiar (float): Magnitude mínima de z-score que ainda caracteriza
                um sinal ativo. O filtro antecipado evita calcular tendências
                para séries que a aplicação descartaria em seguida.

        Returns:
            list[dict[str, Any]]: Uma linha por bucket, com `z` calculado.
                `z` vem `None` quando a fonte nao tem historico suficiente
                (menos de 3 amostras) na janela de base.
        """
        baseline_desde = desde - timedelta(hours=self._baseline_horas)
        # youbora_device tem ~2.900 aparelhos: incluir esse grain transforma
        # "quais fontes estao desviadas agora" numa varredura de milhoes de
        # buckets, estoura os 30 s da Lambda e ainda mistura aparelho com POP.
        # Quem quer o grain de dispositivo usa Recorte, com source explicito.
        excluidas = ["youbora_device"]
        return self._all(
            sql.SQL(
                """
                WITH janela AS MATERIALIZED (
                  SELECT bucket_ts, source, entity, metric, value, hora_brt
                    FROM gold.v_feature_bucket
                   WHERE bucket_ts >= %s AND bucket_ts <= %s
                     AND value IS NOT NULL
                     AND NOT (source = ANY(%s))
                ),
                ultimo AS (
                  SELECT DISTINCT ON (source, entity, metric)
                         bucket_ts, source, entity, metric, value, hora_brt
                    FROM janela
                   ORDER BY source, entity, metric, bucket_ts DESC
                ),
                -- Primeiro calcula apenas o baseline da hora do ULTIMO bucket.
                -- Isso basta para decidir se a serie continua desviada agora;
                -- calcular as seis horas de baseline para todas as series era
                -- o principal custo da rota e estourava os 30 s da Lambda.
                base_ultimo AS (
                  SELECT b.source, b.entity, b.metric, b.hora_brt,
                         avg(b.value)         AS media,
                         stddev_samp(b.value) AS desvio,
                         count(*)             AS n
                    FROM gold.v_feature_bucket b
                    JOIN ultimo u
                      ON u.source = b.source AND u.entity = b.entity
                     AND u.metric = b.metric AND u.hora_brt = b.hora_brt
                   WHERE b.bucket_ts >= %s AND b.bucket_ts < %s
                     AND b.value IS NOT NULL
                     AND NOT (b.source = ANY(%s))
                   GROUP BY b.source, b.entity, b.metric, b.hora_brt
                ),
                ativos AS MATERIALIZED (
                  SELECT u.source, u.entity, u.metric,
                         abs((u.value - b.media) / b.desvio) AS magnitude
                    FROM ultimo u
                    JOIN base_ultimo b
                      ON b.source = u.source AND b.entity = u.entity
                     AND b.metric = u.metric AND b.hora_brt = u.hora_brt
                   WHERE b.desvio IS NOT NULL AND b.desvio <> 0 AND b.n >= 3
                     AND abs((u.value - b.media) / b.desvio) >= %s
                   ORDER BY magnitude DESC
                   LIMIT %s
                ),
                horas_ativas AS (
                  SELECT DISTINCT j.source, j.entity, j.metric, j.hora_brt
                    FROM janela j
                    JOIN ativos a
                      ON a.source = j.source AND a.entity = j.entity
                     AND a.metric = j.metric
                ),
                -- So depois de conhecer os sinais ativos calcula o baseline
                -- das demais horas necessárias para montar seus sparklines.
                base AS (
                  SELECT b.source, b.entity, b.metric, b.hora_brt,
                         avg(b.value)         AS media,
                         stddev_samp(b.value) AS desvio,
                         count(*)             AS n
                    FROM gold.v_feature_bucket b
                    JOIN horas_ativas s
                      ON s.source = b.source AND s.entity = b.entity
                     AND s.metric = b.metric AND s.hora_brt = b.hora_brt
                   WHERE b.bucket_ts >= %s AND b.bucket_ts < %s
                     AND b.value IS NOT NULL
                     AND NOT (b.source = ANY(%s))
                   GROUP BY b.source, b.entity, b.metric, b.hora_brt
                )
                SELECT j.bucket_ts, j.source, j.entity, j.metric, j.value,
                       b.media, b.desvio, b.n,
                       CASE
                         WHEN b.desvio IS NULL OR b.desvio = 0 OR b.n < 3 THEN NULL
                         ELSE (j.value - b.media) / b.desvio
                       END AS z
                  FROM janela j
                  JOIN ativos a
                    ON a.source = j.source AND a.entity = j.entity
                   AND a.metric = j.metric
                  LEFT JOIN base b
                    ON b.source = j.source AND b.entity = j.entity
                   AND b.metric = j.metric AND b.hora_brt = j.hora_brt
                 ORDER BY j.source, j.entity, j.metric, j.bucket_ts
                """
            ),
            [
                desde,
                ate,
                excluidas,
                baseline_desde,
                desde,
                excluidas,
                limiar,
                self._max_series_ativas,
                baseline_desde,
                desde,
                excluidas,
            ],
        )

    def _all(self, instrucao, params: list[Any]) -> list[dict[str, Any]]:
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(instrucao, params)
            return cur.fetchall()
