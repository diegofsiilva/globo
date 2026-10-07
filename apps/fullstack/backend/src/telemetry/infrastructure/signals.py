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

    # As mesmas dimensoes que `GoldRepository.DIMENSOES` expoe para Explorar,
    # Comparar e Recorte. A tela Agora escolhe um subconjunto (`source`,
    # `entity`, `metric`, `tem_jogo`) porque `hora_brt` e `dow` sao o eixo do
    # baseline: filtrar por eles aqui compararia a serie consigo mesma.
    DIMENSOES = ("source", "entity", "metric", "tem_jogo")

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

    @property
    def max_active_series(self) -> int:
        """Teto de series ativas que a consulta considera.

        Returns:
            int: Numero maximo de series que `desvios` chega a avaliar por
                completo. A aplicacao usa isto para saber que a lista pode
                estar truncada na origem, e nao apenas pelo `limit` da rota.
        """
        return self._max_series_ativas

    def desvios(
        self,
        desde: datetime,
        ate: datetime,
        limiar: float = 2.0,
        escopo: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Mede o desvio de cada bucket da janela contra o baseline circadiano.

        O baseline e a media e o desvio-padrao da MESMA hora do dia, apurados
        numa janela anterior -- e o que evita ler o pico normal do horario nobre
        como anomalia toda noite.

        Args:
            desde (datetime): Inicio da janela analisada.
            ate (datetime): Fim da janela analisada.
            limiar (float): Magnitude mínima de z-score que ainda caracteriza
                um sinal ativo. O filtro antecipado evita calcular tendências
                para séries que a aplicação descartaria em seguida.
            escopo (dict[str, str] | None): Filtros de dimensao (`source`,
                `entity`, `metric`, `tem_jogo`) aplicados tanto a janela quanto
                ao baseline. Restringir os dois lados e o que mantem a
                comparacao valida: um baseline de "todas as horas" contra uma
                janela de "so com jogo" mediria a diferenca entre os recortes,
                nao um desvio.

        Returns:
            list[dict[str, Any]]: Uma linha por bucket, com `z` calculado.
                `z` vem `None` quando a fonte nao tem historico suficiente
                (menos de 3 amostras) na janela de base.

        Raises:
            ValueError: Se `escopo` trouxer uma dimensao fora de `DIMENSOES`.
        """
        baseline_desde = desde - timedelta(hours=self._baseline_horas)
        # youbora_device tem ~2.900 aparelhos: incluir esse grain transforma
        # "quais fontes estao desviadas agora" numa varredura de milhoes de
        # buckets, estoura os 30 s da Lambda e ainda mistura aparelho com POP.
        # Quem quer o grain de dispositivo usa Recorte, com source explicito.
        excluidas = ["youbora_device"]

        filtro_janela, params_janela = self._filtros(escopo)
        filtro_historico, params_historico = self._filtros(escopo, alias="h")

        return self._all(
            sql.SQL(
                """
                WITH janela AS MATERIALIZED (
                  SELECT bucket_ts, source, entity, metric, value, hora_brt
                    FROM gold.v_feature_bucket
                   WHERE bucket_ts >= %s AND bucket_ts <= %s
                     AND value IS NOT NULL
                     AND NOT (source = ANY(%s))
                     {filtro_janela}
                ),
                ultimo AS (
                  SELECT DISTINCT ON (source, entity, metric)
                         bucket_ts, source, entity, metric, value, hora_brt
                    FROM janela
                   ORDER BY source, entity, metric, bucket_ts DESC
                ),
                -- Le o historico uma vez. O LATERAL anterior repetia uma busca
                -- no banco para cada serie da janela e excedia o timeout depois
                -- que o dump passou a conter milhoes de buckets.
                --
                -- So as horas do dia que a janela contem. O baseline e por
                -- `hora_brt`, e as duas juncoes abaixo so usam o historico
                -- das horas presentes em `janela`: sem este predicado a CTE
                -- materializava os sete dias inteiros (1 M de buckets numa
                -- carga de seis dias) para aproveitar 1/24 deles, e a view
                -- avaliava `sim.now()` linha a linha -- a consulta sem filtro
                -- de fonte passava dos 15 s do `statement_timeout`. O
                -- resultado e o mesmo; o predicado barato roda antes do filtro
                -- da view e descarta as outras 23 horas.
                historico AS MATERIALIZED (
                  SELECT h.bucket_ts, h.source, h.entity, h.metric,
                         h.hora_brt, h.value
                    FROM gold.v_feature_bucket h
                   WHERE h.bucket_ts >= %s AND h.bucket_ts < %s
                     AND h.value IS NOT NULL
                     AND NOT (h.source = ANY(%s))
                     AND h.hora_brt = ANY(
                           ARRAY(SELECT DISTINCT j.hora_brt FROM janela j)
                         )
                     {filtro_historico}
                ),
                baseline_ultimo AS MATERIALIZED (
                  SELECT h.source, h.entity, h.metric, h.hora_brt,
                         avg(h.value) AS media,
                         stddev_samp(h.value) AS desvio,
                         count(*) AS n
                    FROM historico h
                    JOIN ultimo u
                      ON u.source = h.source AND u.entity = h.entity
                     AND u.metric = h.metric AND u.hora_brt = h.hora_brt
                   GROUP BY h.source, h.entity, h.metric, h.hora_brt
                ),
                avaliados AS MATERIALIZED (
                  SELECT u.bucket_ts, u.source, u.entity, u.metric, u.value,
                         u.hora_brt, b.media, b.desvio, b.n,
                         CASE
                           WHEN b.desvio IS NULL OR b.desvio = 0 OR b.n < 3 THEN NULL
                           ELSE (u.value - b.media) / b.desvio
                         END AS z
                    FROM ultimo u
                    LEFT JOIN baseline_ultimo b
                      ON b.source = u.source AND b.entity = u.entity
                     AND b.metric = u.metric AND b.hora_brt = u.hora_brt
                ),
                ativos AS MATERIALIZED (
                  SELECT source, entity, metric, abs(z) AS magnitude
                    FROM avaliados
                   WHERE z IS NOT NULL AND abs(z) >= %s
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
                    FROM historico b
                    JOIN horas_ativas s
                      ON s.source = b.source AND s.entity = b.entity
                     AND s.metric = b.metric AND s.hora_brt = b.hora_brt
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
            ).format(
                filtro_janela=filtro_janela,
                filtro_historico=filtro_historico,
            ),
            [
                desde,
                ate,
                excluidas,
                *params_janela,
                baseline_desde,
                desde,
                excluidas,
                *params_historico,
                limiar,
                # Uma serie a mais que o teto, de proposito: e assim que a
                # aplicacao distingue "sao exatamente 100 sinais" de "sao 100 e
                # o banco parou de contar". A serie excedente e descartada, mas
                # a sua existencia vira o `truncated` da resposta.
                self._max_series_ativas + 1,
            ],
        )

    def _filtros(
        self, escopo: dict[str, str] | None, alias: str | None = None
    ) -> tuple[sql.Composed, list[Any]]:
        """Traduz o escopo da tela Agora em predicados `AND` parametrizados.

        Args:
            escopo (dict[str, str] | None): Dimensao -> valor, ja filtrado de
                vazios pela camada HTTP.
            alias (str | None): Prefixo da tabela dentro da consulta, quando o
                predicado precisa qualificar a coluna (`h`, `b`).

        Returns:
            tuple[sql.Composed, list[Any]]: Fragmento SQL pronto para
                interpolar e os parametros na mesma ordem.

        Raises:
            ValueError: Se uma dimensao nao estiver em `DIMENSOES`. O nome da
                coluna nunca vem do cliente: e a constante que decide, e o
                valor viaja como parametro.
        """
        if not escopo:
            return sql.SQL(""), []

        predicados: list[sql.Composed] = []
        params: list[Any] = []
        for dimensao, valor in escopo.items():
            if dimensao not in self.DIMENSOES:
                raise ValueError(f"dimensao invalida: {dimensao}")
            coluna = sql.Identifier(alias, dimensao) if alias else sql.Identifier(dimensao)
            predicados.append(sql.SQL("AND {}::text = %s").format(coluna))
            params.append(valor)
        return sql.SQL(" ").join(predicados), params

    def _all(self, instrucao, params: list[Any]) -> list[dict[str, Any]]:
        """Executa a consulta e devolve todas as linhas como dicionarios.

        Args:
            instrucao: Consulta ja composta por `psycopg.sql`.
            params (list[Any]): Parametros na ordem dos `%s` da consulta.

        Returns:
            list[dict[str, Any]]: Linhas do cursor, uma por bucket.
        """
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(instrucao, params)
            return cur.fetchall()
