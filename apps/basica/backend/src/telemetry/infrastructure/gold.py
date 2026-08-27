"""Leitura da camada gold: relogio virtual, series e janelas de incidente.

E o que a v2 nao tinha. As telas do dashboard (Agora, Timeline, Comparar,
Hipoteses) nao consultam evento de sessao -- consultam SERIE de telemetria, e
essa serie mora em `gold.v_feature_bucket`.

Separado de `postgres.py` de proposito: sao dois grains diferentes (evento
individual x bucket agregado de 15 min), com filtros diferentes e telas
diferentes. Um repositorio unico teria dois conjuntos de metodos que nunca se
cruzam, e a `EventFilters` acabaria com campos que so metade dos metodos usa.

Como no outro adaptador, TODA consulta aponta para uma view `v_*`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Clock:
    """O presente virtual, como o banco o enxerga."""

    sim_now: datetime
    speed: float
    updated_at: datetime


class GoldRepository:
    """Le series, janelas e o relogio das views de gold, silver e sim."""

    def __init__(self, pool: ConnectionPool, *, max_points: int = 20_000) -> None:
        """Inicializa o repositorio.

        Args:
            pool (ConnectionPool): Pool de conexao ja aberto.
            max_points (int): Teto de pontos devolvidos numa serie. Protege o
                tempo de resposta (RNF02) e o navegador -- um grafico com 200
                mil pontos trava a aba antes de terminar de desenhar.
        """
        self._pool = pool
        self._teto = max_points

    @property
    def pool(self) -> ConnectionPool:
        """Pool compartilhado com repositorios da mesma aplicacao."""
        return self._pool

    # ----------------------------------------------------------------- #
    # Relogio
    # ----------------------------------------------------------------- #

    def clock(self) -> Clock:
        """Le o instante virtual.

        A tela e marcada "ao vivo", entao ela precisa saber que horas sao no
        mundo virtual. Sem isto, "agora" no dashboard seria o relogio do
        navegador, que nao tem relacao nenhuma com o que o banco esta mostrando
        -- e a tela pareceria vazia sem explicar por que.

        Returns:
            Clock: Instante virtual, velocidade e ultimo reposicionamento.
        """
        linha = self._one(sql.SQL("SELECT sim_now, speed, updated_at FROM sim.v_clock"), [])
        if not linha:
            raise RuntimeError("sim.v_clock vazia: as migrations foram aplicadas?")
        return Clock(
            sim_now=linha["sim_now"],
            speed=float(linha["speed"]),
            updated_at=linha["updated_at"],
        )

    # ----------------------------------------------------------------- #
    # Series
    # ----------------------------------------------------------------- #

    def series(
        self,
        *,
        source: str | None = None,
        entity: str | None = None,
        metric: str | None = None,
        desde: datetime | None = None,
        ate: datetime | None = None,
        janela_horas: int = 24,
        limite: int | None = None,
    ) -> list[dict[str, Any]]:
        """Le pontos de `gold.v_feature_bucket`.

        Args:
            source (str | None): Fonte (prometheus, youbora, rpaas...).
            entity (str | None): Entidade dentro da fonte.
            metric (str | None): Metrica.
            desde (datetime | None): Inicio da janela.
            ate (datetime | None): Fim da janela.
            janela_horas (int): Janela assumida quando nada e informado,
                terminando em `sim.now()`.
            limite (int | None): Teto de pontos.

        Returns:
            list[dict[str, Any]]: Pontos em ordem cronologica.
        """
        onde = [sql.SQL("TRUE")]
        params: list[Any] = []

        for coluna, valor in (("source", source), ("entity", entity), ("metric", metric)):
            if valor:
                onde.append(sql.SQL("{} = %s").format(sql.Identifier(coluna)))
                params.append(valor)

        if desde is None and ate is None:
            # Termina em `sim.now()`, o presente VIRTUAL. Ancorar no relogio de
            # parede devolveria vazio sempre que o simulador estivesse
            # replicando uma janela do passado.
            onde.append(sql.SQL("bucket_ts >= sim.now() - %s"))
            params.append(timedelta(hours=janela_horas))
        else:
            if desde is not None:
                onde.append(sql.SQL("bucket_ts >= %s"))
                params.append(desde)
            if ate is not None:
                onde.append(sql.SQL("bucket_ts <= %s"))
                params.append(ate)

        return self._all(
            sql.SQL(
                """
                SELECT bucket_ts, source, entity, metric, value,
                       hora_brt, dow, tem_jogo
                  FROM gold.v_feature_bucket
                 WHERE {onde}
                 ORDER BY bucket_ts
                 LIMIT %s
                """
            ).format(onde=sql.SQL(" AND ").join(onde)),
            [*params, min(limite or self._teto, self._teto)],
        )

    def lane_series(
        self, sources: list[str], desde: datetime, ate: datetime, *, limite: int = 2000
    ) -> list[dict[str, Any]]:
        """Le pontos de `gold.v_feature_bucket` para um grupo de fontes.

        Usado para montar uma raia da Timeline que agrega mais de uma fonte
        real sob um rotulo so (ex.: "NPAW" cobre `npaw`, `youbora` e
        `youbora_player_live` -- ver `interfaces/http.py::timeline`).

        Args:
            sources (list[str]): Fontes a incluir.
            desde (datetime): Inicio da janela.
            ate (datetime): Fim da janela.
            limite (int): Teto de pontos.

        Returns:
            list[dict[str, Any]]: Pontos em ordem cronologica.
        """
        if not sources:
            return []
        return self._all(
            sql.SQL(
                """
                SELECT bucket_ts, source, entity, metric, value
                  FROM gold.v_feature_bucket
                 WHERE source = ANY(%s) AND bucket_ts >= %s AND bucket_ts <= %s
                 ORDER BY bucket_ts
                 LIMIT %s
                """
            ),
            [sources, desde, ate, min(limite, self._teto)],
        )

    def sources(self) -> list[dict[str, Any]]:
        """Lista as fontes disponiveis e o quao recente e cada uma.

        `ultimo_bucket` e o que sustenta o "fontes com desvio: 3 de 13" do
        painel lateral: uma fonte cujo ultimo bucket ficou muito para tras
        parou de reportar, e isso e diferente de estar reportando normalmente.

        Returns:
            list[dict[str, Any]]: Fontes com contagem e ultimo bucket.
        """
        return self._all(
            sql.SQL(
                """
                WITH fontes AS (
                  SELECT source,
                         count(DISTINCT entity) AS entidades,
                         count(DISTINCT metric) AS metricas
                    FROM gold.v_source_series
                   GROUP BY source
                )
                SELECT f.source, f.entidades, f.metricas,
                       recente.bucket_ts AS ultimo_bucket
                  FROM fontes f
                  LEFT JOIN LATERAL (
                    SELECT bucket_ts
                      FROM gold.v_feature_bucket
                     WHERE source = f.source
                     ORDER BY bucket_ts DESC
                     LIMIT 1
                  ) recente ON true
                 ORDER BY f.source
                """
            ),
            [],
        )

    # ----------------------------------------------------------------- #
    # Janelas
    # ----------------------------------------------------------------- #

    def incidents(
        self,
        *,
        origem: str | None = None,
        desde: datetime | None = None,
        ate: datetime | None = None,
        incluir_derivados: bool = False,
        limite: int = 100,
    ) -> list[dict[str, Any]]:
        """Le janelas de incidente.

        Args:
            origem (str | None): `incidents`, `incident_label` ou `detector`.
            desde (datetime | None): So janelas que tocam a partir daqui
                (`ts_end >= desde`). Sem valor, nao filtra por inicio.
            ate (datetime | None): So janelas que tocam ate aqui
                (`ts_start <= ate`). Sem valor, nao filtra por fim.
            incluir_derivados (bool): Se inclui os rotulos `detector-derived`.
            limite (int): Teto de janelas.

        Returns:
            list[dict[str, Any]]: Janelas, da mais recente para a mais antiga.
        """
        onde = [sql.SQL("TRUE")]
        params: list[Any] = []

        if origem:
            onde.append(sql.SQL("origem = %s"))
            params.append(origem)

        if desde is not None:
            onde.append(sql.SQL("ts_end >= %s"))
            params.append(desde)
        if ate is not None:
            onde.append(sql.SQL("ts_start <= %s"))
            params.append(ate)

        if not incluir_derivados:
            # Sete dos vinte rotulos de incident_label foram criados olhando a
            # saida do PROPRIO Argus. Avaliar um detector novo contra eles mede
            # concordancia com o baseline, e nao acuracia -- um modelo que
            # encontrasse incidentes reais que o Argus perdeu seria penalizado.
            #
            # Por isso o padrao e EXCLUIR, e incluir exige pedir explicitamente.
            onde.append(sql.SQL("(provenance IS NULL OR provenance <> 'detector-derived')"))

        return self._all(
            sql.SQL(
                """
                SELECT window_id, ts_start, ts_end, origem, ref_id,
                       verdict, severity, provenance
                  FROM gold.v_incident_window
                 WHERE {onde}
                 ORDER BY ts_start DESC
                 LIMIT %s
                """
            ).format(onde=sql.SQL(" AND ").join(onde)),
            [*params, limite],
        )

    def live_events(self, *, limite: int = 50) -> list[dict[str, Any]]:
        """Le o calendario de transmissoes ao vivo.

        Agrupa por `event_key` e nao por `ts_start`: `tid` 994 e 995 sao feeds
        SIMULTANEOS com jogos diferentes -- a Globo transmite partidas distintas
        em pracas distintas no mesmo horario. Agrupar por horario funde dois
        jogos num so.

        Returns:
            list[dict[str, Any]]: Transmissoes, da mais recente para a mais
                antiga, com os feeds de cada confronto agregados.
        """
        return self._all(
            sql.SQL(
                """
                SELECT event_key,
                       min(ts_start) AS ts_start,
                       max(ts_end)   AS ts_end,
                       min(competition) AS competition,
                       min(team_home)   AS team_home,
                       min(team_away)   AS team_away,
                       array_agg(DISTINCT tid ORDER BY tid) AS feeds
                  FROM gold.v_live_event_window
                 GROUP BY event_key
                 ORDER BY ts_start DESC
                 LIMIT %s
                """
            ),
            [limite],
        )

    def deploy_events(
        self, *, desde: datetime | None = None, ate: datetime | None = None, limite: int = 200
    ) -> list[dict[str, Any]]:
        """Le eventos de mudanca de plataforma (deploy e afins) de `gold.v_deploy_event`.

        So cobre deploy (fonte Tsuru, ver 018_deploy_events.sql) -- o dataset
        nao tem log discreto de mudanca para autoscale nem WAF, so serie de
        metrica.

        Args:
            desde (datetime | None): Inicio da janela, por `started_at`.
            ate (datetime | None): Fim da janela.
            limite (int): Teto de eventos.

        Returns:
            list[dict[str, Any]]: Eventos, do mais recente para o mais antigo.
        """
        onde = [sql.SQL("TRUE")]
        params: list[Any] = []
        if desde is not None:
            onde.append(sql.SQL("started_at >= %s"))
            params.append(desde)
        if ate is not None:
            onde.append(sql.SQL("started_at <= %s"))
            params.append(ate)

        return self._all(
            sql.SQL(
                """
                SELECT event_id, kind, target_type, target_value, owner,
                       started_at, ended_at, duration_ms, error
                  FROM gold.v_deploy_event
                 WHERE {onde}
                 ORDER BY started_at DESC
                 LIMIT %s
                """
            ).format(onde=sql.SQL(" AND ").join(onde)),
            [*params, limite],
        )

    def janela_estavel(
        self, *, duracao: timedelta, antes: datetime, max_passos: int = 200
    ) -> dict[str, datetime] | None:
        """Acha a janela mais recente de `duracao`, terminando antes de `antes`,
        que nao sobrepoe nenhuma `gold.v_incident_window`.

        Passo a passo -- caminha para tras em incrementos de `duracao`,
        checando sobreposicao a cada passo -- em vez de uma unica consulta
        combinatoria: mantem o SQL simples, ao custo de ate `max_passos`
        idas ao banco no pior caso (janela sem historico estavel suficiente).

        Args:
            duracao (timedelta): Tamanho da janela procurada.
            antes (datetime): Nao propor janela terminando depois disto.
            max_passos (int): Teto de tentativas antes de desistir.

        Returns:
            dict[str, datetime] | None: `{"ts_start", "ts_end"}` da janela
                encontrada, ou `None` se nenhuma das `max_passos` tentativas
                ficou livre de incidente.
        """
        fim = antes
        for _ in range(max_passos):
            inicio = fim - duracao
            sobrepoe = self._one(
                sql.SQL(
                    """
                    SELECT 1 FROM gold.v_incident_window
                     WHERE ts_start < %s AND ts_end > %s
                     LIMIT 1
                    """
                ),
                [fim, inicio],
            )
            if sobrepoe is None:
                return {"ts_start": inicio, "ts_end": fim}
            fim = inicio
        return None

    def ultimo_pico_ao_vivo(self, *, antes: datetime) -> dict[str, Any] | None:
        """A transmissao ao vivo mais recente que comecou antes de `antes`.

        Args:
            antes (datetime): Nao propor evento comecando depois disto.

        Returns:
            dict[str, Any] | None: O confronto (feeds agregados por
                `event_key`, mesmo cuidado de `live_events`), ou `None`.
        """
        return self._one(
            sql.SQL(
                """
                SELECT event_key,
                       min(ts_start)    AS ts_start,
                       max(ts_end)      AS ts_end,
                       min(competition) AS competition,
                       min(team_home)   AS team_home,
                       min(team_away)   AS team_away
                  FROM gold.v_live_event_window
                 WHERE ts_start <= %s
                 GROUP BY event_key
                 ORDER BY max(ts_end) DESC
                 LIMIT 1
                """
            ),
            [antes],
        )

    def anomalies(self, *, run_id: int | None = None, limite: int = 200) -> list[dict[str, Any]]:
        """Le as anomalias de uma execucao do detector.

        Devolve lista vazia enquanto nao houver detector (decisao 7 do plano):
        a tabela existe, ninguem a popula ainda. A rota existir desde ja e o que
        permite o dashboard ser escrito contra o contrato final.

        Args:
            run_id (int | None): Execucao. None traz a mais recente.
            limite (int): Teto de anomalias.

        Returns:
            list[dict[str, Any]]: Anomalias, da de maior score para a menor.
        """
        onde = [sql.SQL("TRUE")]
        params: list[Any] = []
        if run_id is not None:
            onde.append(sql.SQL("run_id = %s"))
            params.append(run_id)
        else:
            onde.append(sql.SQL("run_id = (SELECT max(run_id) FROM detect.v_run)"))

        return self._all(
            sql.SQL(
                """
                SELECT run_id, bucket_ts, source, entity, metric, z, score, n_sources
                  FROM detect.v_anomaly
                 WHERE {onde}
                 ORDER BY score DESC NULLS LAST, bucket_ts DESC
                 LIMIT %s
                """
            ).format(onde=sql.SQL(" AND ").join(onde)),
            [*params, limite],
        )

    # ----------------------------------------------------------------- #
    # Internos
    # ----------------------------------------------------------------- #

    def _all(self, instrucao, params: list[Any]) -> list[dict[str, Any]]:
        """Executa e devolve todas as linhas.

        Args:
            instrucao: Instrucao composta.
            params (list[Any]): Parametros de bind.

        Returns:
            list[dict[str, Any]]: Linhas.
        """
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(instrucao, params)
            return cur.fetchall()

    def _one(self, instrucao, params: list[Any]) -> dict[str, Any] | None:
        """Executa e devolve a primeira linha.

        Args:
            instrucao: Instrucao composta.
            params (list[Any]): Parametros de bind.

        Returns:
            dict[str, Any] | None: Primeira linha, ou None.
        """
        linhas = self._all(instrucao, params)
        return linhas[0] if linhas else None
