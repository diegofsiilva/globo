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
from collections.abc import Sequence
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

    # ----------------------------------------------------------------- #
    # Agregacoes sobre a serie (telas Explorar e Recorte)
    #
    # Estas telas foram especificadas sobre evento por sessao (device_model,
    # route_path, event_name -- ver rotas-frontend.md 4.4.3), mas o dump do
    # Argus nao tem essa granularidade: nao existe `event.parquet`, e
    # `silver.session_event` so recebe o que entra pela API de ingestao.
    #
    # O que o dump TEM e a mesma telemetria agregada por hora e dimensao, ja
    # promovida a `gold.feature_bucket` (18,2 M de pontos em signal_point,
    # incluindo youbora_device com 2.897 aparelhos). As agregacoes abaixo
    # servem as telas a partir dai, com numero real, em vez de deixa-las
    # vazias ou preenche-las com dado inventado.
    # ----------------------------------------------------------------- #

    #: Dimensoes agrupaveis de `gold.v_feature_bucket`. Lista fechada: o nome
    #: entra na consulta como identificador, entao nao pode vir do cliente.
    DIMENSOES = ("source", "entity", "metric", "hora_brt", "dow", "tem_jogo")

    #: Fontes no grain de aparelho. `youbora_device` tem ~2.900 entidades; um
    #: `GROUP BY metric` sem recorte de fonte varre esses aparelhos para somar
    #: a mesma telemetria que `youbora` ja agrega. So entram quando a consulta
    #: pede `source=` explicitamente -- Recorte e o agrupamento "Dispositivo".
    FONTES_GRAIN_DISPOSITIVO = ("youbora_device",)

    #: Marcas de nome que indicam metrica de TAXA, e nao de contagem.
    #: `gold.feature_bucket` nao tem coluna de unidade, entao o nome e o unico
    #: sinal disponivel.
    MARCAS_DE_TAXA = ("_pct", "_rate", "_ms", "_avg", "ratio", "_p50", "_p95")

    @classmethod
    def _agregacao(cls, metric: str | None, *, agrupa_por_metrica: bool = False) -> sql.SQL:
        """Escolhe entre somar e tirar media, pelo tipo da metrica.

        Somar taxa nao significa nada: seis baldes de 0,55% nao dao 3,3%.
        Metrica de contagem (sessions, errors, requests) soma; taxa, percentual,
        duracao e media entram por AVG.

        Quando a consulta AGRUPA por metrica, cada grupo tem uma unidade
        diferente e nao existe uma escolha unica correta -- ai a decisao vai
        para dentro do SQL, linha a linha. Sem isso, um breakdown por metrica
        sem filtro somava taxa com contagem no mesmo resultado.

        Args:
            metric (str | None): Metrica filtrada, quando houver.
            agrupa_por_metrica (bool): Se `metric` esta no GROUP BY.

        Returns:
            sql.SQL: Expressao de agregacao aplicada sobre `value`.
        """
        if agrupa_por_metrica and not metric:
            # Regex e nao LIKE: o `%` do LIKE colide com o placeholder do
            # psycopg (`'%_pct%'` vira o placeholder invalido `%_`).
            padrao = "|".join(marca.replace("_", "[_]") for marca in cls.MARCAS_DE_TAXA)
            return sql.SQL(
                "CASE WHEN metric ~ {padrao} THEN avg(value) ELSE sum(value) END"
            ).format(padrao=sql.Literal(padrao))
        if metric and any(marca in metric for marca in cls.MARCAS_DE_TAXA):
            return sql.SQL("avg(value)")
        return sql.SQL("sum(value)")

    def _janela(
        self,
        desde: datetime | None,
        ate: datetime | None,
        janela_horas: int,
        janela_minutos: int | None = None,
    ) -> tuple[list[sql.SQL], list[Any]]:
        """Monta o recorte temporal, ancorado em `sim.now()` quando ausente."""
        onde: list[sql.SQL] = []
        params: list[Any] = []
        if desde is None and ate is None:
            onde.append(sql.SQL("bucket_ts >= sim.now() - %s"))
            if janela_minutos is not None:
                params.append(timedelta(minutes=janela_minutos))
            else:
                params.append(timedelta(hours=janela_horas))
        else:
            if desde is not None:
                onde.append(sql.SQL("bucket_ts >= %s"))
                params.append(desde)
            if ate is not None:
                onde.append(sql.SQL("bucket_ts <= %s"))
                params.append(ate)
        return onde, params

    def _escopo(
        self, escopo: dict[str, str] | None
    ) -> tuple[list[sql.SQL], list[Any]]:
        """Traduz o escopo da barra de filtros em predicados."""
        onde: list[sql.SQL] = []
        params: list[Any] = []
        for coluna, valor in (escopo or {}).items():
            if coluna not in self.DIMENSOES or not valor:
                continue
            onde.append(sql.SQL("{}::text = %s").format(sql.Identifier(coluna)))
            params.append(valor)
        return onde, params

    def _exceto_grain_dispositivo(
        self, escopo: dict[str, str] | None
    ) -> tuple[list[sql.SQL], list[Any]]:
        """Omite fontes no grain de aparelho quando a consulta nao as pediu."""
        if (escopo or {}).get("source"):
            return [], []
        return (
            [sql.SQL("NOT (source = ANY(%s))")],
            [list(self.FONTES_GRAIN_DISPOSITIVO)],
        )

    def serie_facets(
        self,
        campos: Sequence[str],
        *,
        limite: int = 50,
        janela_horas: int = 24,
    ) -> dict[str, list[str]]:
        """Valores distintos de cada dimensao, para montar os filtros.

        Janela e varredura unica, os dois de proposito. A versao anterior fazia
        um `GROUP BY` sem recorte temporal, uma consulta por campo -- quatro
        varreduras da particao inteira, 30 s de timeout na Lambda. Pior que
        lento, era ERRADO: oferecia no filtro valores que sumiram ha semanas e
        que devolvem tela vazia quando escolhidos. A faceta descreve a MESMA
        janela que as telas consultam.

        Args:
            campos (Sequence[str]): Dimensoes pedidas.
            limite (int): Teto de valores por dimensao.
            janela_horas (int): Recorte para tras a partir de `sim.now()`.

        Returns:
            dict[str, list[str]]: Valores por dimensao, os mais frequentes antes.

        Raises:
            ValueError: Se a dimensao nao for agrupavel.
        """
        for campo in campos:
            if campo not in self.DIMENSOES:
                raise ValueError(f"dimensao invalida: {campo}")
        if not campos:
            return {}

        # O `VALUES` desdobra cada linha da janela em uma tupla (campo, valor)
        # por dimensao pedida, entao um unico scan alimenta todas as facetas.
        # Os nomes vem de DIMENSOES (constante da classe), nunca do cliente.
        pares = sql.SQL(", ").join(
            sql.SQL("({rotulo}, {coluna}::text)").format(
                rotulo=sql.Literal(campo), coluna=sql.Identifier(campo)
            )
            for campo in campos
        )

        linhas = self._all(
            sql.SQL(
                """
                WITH janela AS (
                  SELECT {colunas}
                    FROM gold.v_feature_bucket
                   WHERE bucket_ts >= sim.now() - %s
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
                colunas=sql.SQL(", ").join(sql.Identifier(c) for c in campos),
                pares=pares,
            ),
            [timedelta(hours=janela_horas), limite],
        )

        resultado: dict[str, list[str]] = {campo: [] for campo in campos}
        for linha in linhas:
            resultado[linha["campo"]].append(linha["valor"])
        return resultado

    def serie_breakdown(
        self,
        *,
        dimension: str,
        metric: str | None = None,
        desde: datetime | None = None,
        ate: datetime | None = None,
        escopo: dict[str, str] | None = None,
        janela_horas: int = 24,
        janela_minutos: int | None = None,
        limite: int = 100,
    ) -> dict[str, Any]:
        """Agrupa a serie por uma dimensao.

        Returns:
            dict[str, Any]: `dimension`, `metric`, `total` e `groups`.

        Raises:
            ValueError: Se a dimensao nao for agrupavel.
        """
        if dimension not in self.DIMENSOES:
            raise ValueError(f"dimensao invalida: {dimension}")

        onde = [sql.SQL("TRUE")]
        params: list[Any] = []
        if metric:
            onde.append(sql.SQL("metric = %s"))
            params.append(metric)
        for bloco, valores in (
            self._janela(desde, ate, janela_horas, janela_minutos),
            self._escopo(escopo),
            self._exceto_grain_dispositivo(escopo),
        ):
            onde.extend(bloco)
            params.extend(valores)

        grupos = self._all(
            sql.SQL(
                """
                SELECT {coluna}::text AS key,
                       {agregacao} AS value,
                       count(*)    AS points
                  FROM gold.v_feature_bucket
                 WHERE {onde}
                 GROUP BY 1
                 ORDER BY value DESC NULLS LAST
                 LIMIT %s
                """
            ).format(
                coluna=sql.Identifier(dimension),
                agregacao=self._agregacao(metric, agrupa_por_metrica=dimension == "metric"),
                onde=sql.SQL(" AND ").join(onde),
            ),
            [*params, limite],
        )
        total = sum(linha["value"] or 0 for linha in grupos)
        for linha in grupos:
            linha["share"] = ((linha["value"] or 0) / total) if total else 0.0
        return {"dimension": dimension, "metric": metric, "total": total, "groups": grupos}

    def serie_timeseries(
        self,
        *,
        metric: str | None = None,
        interval_minutes: int = 60,
        desde: datetime | None = None,
        ate: datetime | None = None,
        escopo: dict[str, str] | None = None,
        janela_horas: int = 24,
        janela_minutos: int | None = None,
    ) -> dict[str, Any]:
        """Serie temporal agregada, em baldes de `interval_minutes`."""
        onde = [sql.SQL("TRUE")]
        params: list[Any] = []
        if metric:
            onde.append(sql.SQL("metric = %s"))
            params.append(metric)
        for bloco, valores in (
            self._janela(desde, ate, janela_horas, janela_minutos),
            self._escopo(escopo),
            self._exceto_grain_dispositivo(escopo),
        ):
            onde.extend(bloco)
            params.extend(valores)

        # `date_bin` alinha o balde a uma origem fixa, entao janelas diferentes
        # devolvem as MESMAS bordas -- e o que deixa duas consultas
        # comparaveis ponto a ponto na tela Comparar.
        #
        # Agrupa tambem por METRICA e devolve `by_metric` por balde. A tela
        # Explorar desenha volume e erro na mesma serie, e sem a quebra por
        # metrica ela precisaria de uma segunda consulta por ponto.
        linhas = self._all(
            sql.SQL(
                """
                SELECT date_bin(%s, bucket_ts, TIMESTAMPTZ '2026-01-01') AS bucket,
                       metric,
                       {agregacao} AS value,
                       count(*)    AS points
                  FROM gold.v_feature_bucket
                 WHERE {onde}
                 GROUP BY 1, 2
                 ORDER BY 1, 2
                 LIMIT %s
                """
            ).format(
                agregacao=self._agregacao(None, agrupa_por_metrica=True),
                onde=sql.SQL(" AND ").join(onde),
            ),
            [timedelta(minutes=interval_minutes), *params, self._teto],
        )

        baldes: dict[Any, dict[str, Any]] = {}
        for linha in linhas:
            balde = baldes.setdefault(
                linha["bucket"],
                {"bucket": linha["bucket"], "value": 0.0, "points": 0, "by_metric": {}},
            )
            balde["by_metric"][linha["metric"]] = linha["value"]
            balde["points"] += linha["points"]
            # `value` do balde e a metrica pedida; sem filtro, fica a soma das
            # metricas de contagem (taxa nao entra em soma).
            if metric is None:
                if not any(marca in linha["metric"] for marca in self.MARCAS_DE_TAXA):
                    balde["value"] += linha["value"] or 0
            elif linha["metric"] == metric:
                balde["value"] = linha["value"]

        ordenados = [baldes[chave] for chave in sorted(baldes)]
        return {
            "interval_minutes": interval_minutes,
            "metric": metric,
            "total": sum(balde["value"] or 0 for balde in ordenados),
            "buckets": ordenados,
        }

    def serie_crosstab(
        self,
        *,
        dimension_x: str,
        dimension_y: str,
        metric: str | Sequence[str] | None = None,
        desde: datetime | None = None,
        ate: datetime | None = None,
        escopo: dict[str, str] | None = None,
        janela_horas: int = 24,
        janela_minutos: int | None = None,
        limite: int = 400,
    ) -> dict[str, Any]:
        """Cruza duas dimensoes da serie, para o heatmap do Recorte.

        Raises:
            ValueError: Se alguma das dimensoes nao for agrupavel.
        """
        for nome in (dimension_x, dimension_y):
            if nome not in self.DIMENSOES:
                raise ValueError(f"dimensao invalida: {nome}")

        metricas = (
            [metric]
            if isinstance(metric, str)
            else list(metric)
            if metric
            else []
        )
        varias_metricas = len(metricas) > 1

        onde = [sql.SQL("TRUE")]
        params: list[Any] = []
        if len(metricas) == 1:
            onde.append(sql.SQL("metric = %s"))
            params.append(metricas[0])
        elif varias_metricas:
            onde.append(sql.SQL("metric = ANY(%s)"))
            params.append(metricas)
        for bloco, valores in (
            self._janela(desde, ate, janela_horas, janela_minutos),
            self._escopo(escopo),
            self._exceto_grain_dispositivo(escopo),
        ):
            onde.extend(bloco)
            params.extend(valores)

        if varias_metricas:
            celulas = self._all(
                sql.SQL(
                    """
                    SELECT {x}::text AS x, {y}::text AS y, metric,
                           {agregacao} AS value,
                           count(*)    AS points
                      FROM gold.v_feature_bucket
                     WHERE {onde}
                     GROUP BY 1, 2, 3
                     ORDER BY value DESC NULLS LAST
                     LIMIT %s
                    """
                ).format(
                    x=sql.Identifier(dimension_x),
                    y=sql.Identifier(dimension_y),
                    agregacao=self._agregacao(None, agrupa_por_metrica=True),
                    onde=sql.SQL(" AND ").join(onde),
                ),
                [*params, limite],
            )
        else:
            celulas = self._all(
                sql.SQL(
                    """
                    SELECT {x}::text AS x, {y}::text AS y,
                           {agregacao} AS value,
                           count(*)    AS points
                      FROM gold.v_feature_bucket
                     WHERE {onde}
                     GROUP BY 1, 2
                     ORDER BY value DESC NULLS LAST
                     LIMIT %s
                    """
                ).format(
                    x=sql.Identifier(dimension_x),
                    y=sql.Identifier(dimension_y),
                    agregacao=self._agregacao(
                        metricas[0] if metricas else None,
                        agrupa_por_metrica="metric" in (dimension_x, dimension_y),
                    ),
                    onde=sql.SQL(" AND ").join(onde),
                ),
                [*params, limite],
            )
        return {
            "dimension_x": dimension_x,
            "dimension_y": dimension_y,
            "metric": metricas[0] if len(metricas) == 1 else (metricas or None),
            "cells": celulas,
        }

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
        # `DISTINCT ON (source, entity, metric, bucket_ts)` nao muda o grain da
        # tabela -- o ganho e o LIMIT por FONTE, nao global. Sem isso, a raia
        # mais densa (youbora) come o teto e as outras saem vazias.
        teto = min(limite, self._teto)
        return self._all(
            sql.SQL(
                """
                SELECT bucket_ts, source, entity, metric, value
                  FROM (
                    SELECT bucket_ts, source, entity, metric, value,
                           row_number() OVER (
                             PARTITION BY source ORDER BY bucket_ts
                           ) AS posicao
                      FROM gold.v_feature_bucket
                     WHERE source = ANY(%s)
                       AND bucket_ts >= %s AND bucket_ts <= %s
                  ) ranqueado
                 WHERE posicao <= %s
                 ORDER BY bucket_ts
                """
            ),
            [sources, desde, ate, teto],
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
        # Uma consulta so: generate_series anda os mesmos passos que o laco
        # anterior, e o NOT EXISTS rejeita o que sobrepoe incidente. Ate 200
        # idas ao banco (o pior caso antigo) cabem num unico scan de
        # incident_window, que tem dezenas de linhas, nao milhoes.
        linha = self._one(
            sql.SQL(
                """
                WITH passos AS (
                  SELECT n,
                         %s - (n * %s)       AS ts_end,
                         %s - ((n + 1) * %s) AS ts_start
                    FROM generate_series(0, %s) AS n
                )
                SELECT ts_start, ts_end
                  FROM passos p
                 WHERE NOT EXISTS (
                         SELECT 1 FROM gold.v_incident_window i
                          WHERE i.ts_start < p.ts_end AND i.ts_end > p.ts_start
                       )
                 ORDER BY n
                 LIMIT 1
                """
            ),
            [antes, duracao, antes, duracao, max_passos - 1],
        )
        if linha is None:
            return None
        return {"ts_start": linha["ts_start"], "ts_end": linha["ts_end"]}

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
