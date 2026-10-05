"""Porta das ferramentas de investigacao e um adaptador sobre fixtures.

A porta e o que o agente enxerga: tres funcoes com argumentos declarados. O
adaptador que le `silver.analysis_fact_version` e trabalho da pessoa dos dados
(Dia 4 do plano). Este modulo entrega o contrato que esse adaptador precisa
cumprir e um dublê sobre arquivo JSON, para que o ciclo do agente possa ser
construido e testado antes do acesso real ao banco.

O dublê repete as duas invariantes que o adaptador real tambem deve garantir:
nenhum fato com `available_at > sim_now` aparece, e nenhum fato fora da janela
do recorte entra numa resposta. Elas estao aqui para que os testes do agente
falhem quando o ciclo tentar olhar o futuro -- nao para substituir a barreira
que vive no banco.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Protocol

from argus_agente.contrato import (
    ItemInventario,
    LinhaDeFato,
    Recorte,
    RespostaDeFerramenta,
)

AGREGACOES = ("bruto", "media_por_bucket")


class ArgumentoInvalido(ValueError):
    """O modelo pediu uma ferramenta com argumentos que o contrato nao aceita."""


class Ferramentas(Protocol):
    """As tres consultas que o agente pode fazer dentro de um recorte."""

    def inventario(self, *, source: str | None = None) -> tuple[ItemInventario, ...]:
        """Lista as series disponiveis, opcionalmente de uma unica fonte."""
        ...

    def serie(
        self,
        *,
        source: str,
        entity: str,
        metric: str,
        inicio: dt.datetime,
        fim: dt.datetime,
        dimension_type: str | None = None,
        dimension_value: str | None = None,
        agregacao: str = "bruto",
        limite: int = 200,
    ) -> RespostaDeFerramenta:
        """Devolve os pontos de uma metrica no periodo, cada um com `fact_id`."""
        ...

    def contexto(
        self,
        *,
        tipos: tuple[str, ...],
        inicio: dt.datetime,
        fim: dt.datetime,
        limite: int = 200,
    ) -> RespostaDeFerramenta:
        """Devolve fatos nao metricos do periodo, como deploys e eventos ao vivo."""
        ...


class FerramentasDeFixture:
    """Adaptador de desenvolvimento: le os fatos de um arquivo JSON.

    Serve para construir e testar o ciclo do agente sem banco. O formato do
    arquivo e o mesmo de `LinhaDeFato`, com `event_start` e `available_at` em
    ISO-8601.
    """

    def __init__(self, recorte: Recorte, fatos: list[dict[str, Any]]) -> None:
        """Guarda o recorte e materializa os fatos elegiveis uma unica vez.

        Args:
            recorte (Recorte): Identidade e janela do conjunto visivel.
            fatos (list[dict[str, Any]]): Fatos crus do arquivo de fixture.
        """
        self.recorte = recorte
        todos = tuple(_linha(bruto) for bruto in fatos)
        self._fatos = tuple(linha for linha in todos if _elegivel(linha, recorte))
        self._adiados = _lacunas_de_cobertura(todos, recorte)

    @classmethod
    def de_arquivo(cls, caminho: Path, recorte: Recorte) -> FerramentasDeFixture:
        """Carrega um arquivo de fixture.

        Args:
            caminho (Path): Arquivo JSON com a lista de fatos.
            recorte (Recorte): Recorte aplicado na carga.

        Returns:
            FerramentasDeFixture: Adaptador pronto para uso.
        """
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return cls(recorte, dados["fatos"])

    @property
    def lacunas_de_cobertura(self) -> tuple[dict[str, Any], ...]:
        """Series da janela que so ficam disponiveis depois do `sim_now`."""
        return self._adiados

    @property
    def fatos(self) -> tuple[LinhaDeFato, ...]:
        """Os fatos que sobreviveram ao corte temporal do recorte."""
        return self._fatos

    def inventario(self, *, source: str | None = None) -> tuple[ItemInventario, ...]:
        """Agrupa os fatos elegiveis por serie e conta cobertura."""
        grupos: dict[tuple[str, str, str, str | None], list[LinhaDeFato]] = {}
        for linha in self._fatos:
            if linha.kind != "metric":
                continue
            if source and linha.source != source:
                continue
            chave = (linha.source, linha.entity, linha.metric, linha.dimension_type)
            grupos.setdefault(chave, []).append(linha)
        itens = []
        for (fonte, entidade, metrica, dimensao), linhas in sorted(grupos.items()):
            instantes = sorted(linha.event_start for linha in linhas)
            atrasos = [
                int((linha.available_at - linha.event_start).total_seconds())
                for linha in linhas
            ]
            itens.append(
                ItemInventario(
                    source=fonte,
                    entity=entidade,
                    metric=metrica,
                    dimension_type=dimensao,
                    unidade=None,
                    pontos=len(linhas),
                    primeiro_evento=instantes[0],
                    ultimo_evento=instantes[-1],
                    buckets_vazios=_buckets_vazios(instantes),
                    atraso_tipico_segundos=sorted(atrasos)[len(atrasos) // 2],
                )
            )
        return tuple(itens)

    def serie(
        self,
        *,
        source: str,
        entity: str,
        metric: str,
        inicio: dt.datetime,
        fim: dt.datetime,
        dimension_type: str | None = None,
        dimension_value: str | None = None,
        agregacao: str = "bruto",
        limite: int = 200,
    ) -> RespostaDeFerramenta:
        """Filtra os pontos de uma metrica e aplica o teto de linhas."""
        if agregacao not in AGREGACOES:
            raise ArgumentoInvalido(f"agregacao desconhecida: {agregacao}")
        selecionadas = [
            linha
            for linha in self._fatos
            if linha.kind == "metric"
            and linha.source == source
            and linha.entity == entity
            and linha.metric == metric
            and (dimension_type is None or linha.dimension_type == dimension_type)
            and (dimension_value is None or linha.dimension_value == dimension_value)
            and inicio <= linha.event_start <= fim
        ]
        selecionadas.sort(key=lambda linha: (linha.event_start, linha.fact_id))
        if not selecionadas:
            return RespostaDeFerramenta(
                linhas=(),
                vazia_porque=self._porque_vazio(source, entity, metric),
            )
        if agregacao == "media_por_bucket":
            selecionadas = _media_por_hora(selecionadas)
        truncada = len(selecionadas) > limite
        return RespostaDeFerramenta(
            linhas=tuple(selecionadas[:limite]), truncada=truncada
        )

    def _porque_vazio(self, source: str, entity: str, metric: str) -> str:
        """Explica uma resposta vazia sem deixar o modelo adivinhar o motivo.

        Separar "a serie nao existe", "existe mas nao neste periodo" e "existe e
        ainda nao chegou" e o que permite ao agente registrar a lacuna com o
        motivo certo, em vez de concluir que a metrica esta normal.
        """
        adiada = next(
            (
                lacuna
                for lacuna in self._adiados
                if lacuna["source"] == source and lacuna["metric"] == metric
            ),
            None,
        )
        if adiada:
            return (
                f"a serie existe nesta janela, mas so fica disponivel em "
                f"{adiada['disponivel_a_partir_de']}, depois do presente simulado"
            )
        existe_serie = any(
            linha.source == source and linha.entity == entity and linha.metric == metric
            for linha in self._fatos
        )
        if existe_serie:
            return "a serie existe no recorte, mas nao tem ponto no periodo pedido"
        if any(linha.source == source for linha in self._fatos):
            return (
                f"a fonte {source} esta no recorte, mas nao com esta entidade e metrica"
            )
        return f"a fonte {source} nao esta no recorte"

    def contexto(
        self,
        *,
        tipos: tuple[str, ...],
        inicio: dt.datetime,
        fim: dt.datetime,
        limite: int = 200,
    ) -> RespostaDeFerramenta:
        """Filtra fatos nao metricos por tipo e periodo."""
        if not tipos:
            raise ArgumentoInvalido("contexto exige ao menos um tipo")
        # `kind` no silver so distingue 'metric' de 'context'. O tipo util para
        # quem investiga e o nome do fato de contexto -- 'deploy', 'live_event'
        # --, que vive em `metric`, ou a fonte que o emitiu.
        alvos = {tipo.strip().lower() for tipo in tipos}
        contexto = [linha for linha in self._fatos if linha.kind == "context"]
        selecionadas = [
            linha
            for linha in contexto
            if (linha.metric.lower() in alvos or linha.source.lower() in alvos)
            and inicio <= linha.event_start <= fim
        ]
        selecionadas.sort(key=lambda linha: (linha.event_start, linha.fact_id))
        if not selecionadas:
            disponiveis = sorted({linha.metric for linha in contexto})
            motivo = (
                f"nenhum fato dos tipos {sorted(alvos)} no periodo; "
                f"tipos de contexto presentes no recorte: {disponiveis or 'nenhum'}"
            )
            return RespostaDeFerramenta(linhas=(), vazia_porque=motivo)
        truncada = len(selecionadas) > limite
        return RespostaDeFerramenta(
            linhas=tuple(selecionadas[:limite]), truncada=truncada
        )


def _linha(bruto: dict[str, Any]) -> LinhaDeFato:
    """Converte um registro do arquivo em `LinhaDeFato`."""
    return LinhaDeFato(
        fact_id=bruto["fact_id"],
        source=bruto["source"],
        entity=bruto["entity"],
        metric=bruto["metric"],
        event_start=dt.datetime.fromisoformat(bruto["event_start"]),
        available_at=dt.datetime.fromisoformat(bruto["available_at"]),
        value=bruto.get("value"),
        dimension_type=bruto.get("dimension_type"),
        dimension_value=bruto.get("dimension_value"),
        sample_size=bruto.get("sample_size"),
        kind=bruto.get("kind", "metric"),
        fact_ids=(bruto["fact_id"],),
    )


def _lacunas_de_cobertura(
    todos: tuple[LinhaDeFato, ...], recorte: Recorte
) -> tuple[dict[str, Any], ...]:
    """Resume o que a janela tem e o presente simulado ainda nao alcancou.

    Devolve fonte, entidade, metrica e o primeiro instante de disponibilidade.
    Nenhum valor atravessa: o agente fica sabendo que existe dado a caminho,
    como saberia pela cadencia da fonte, sem poder usa-lo.
    """
    adiados: dict[tuple[str, str, str], dt.datetime] = {}
    for linha in todos:
        if linha.available_at <= recorte.sim_now:
            continue
        if not recorte.janela_inicio <= linha.event_start <= recorte.janela_fim:
            continue
        chave = (linha.source, linha.entity, linha.metric)
        anterior = adiados.get(chave)
        if anterior is None or linha.available_at < anterior:
            adiados[chave] = linha.available_at
    return tuple(
        {
            "source": fonte,
            "entity": entidade,
            "metric": metrica,
            "disponivel_a_partir_de": instante.isoformat(),
        }
        for (fonte, entidade, metrica), instante in sorted(adiados.items())
    )


def _elegivel(linha: LinhaDeFato, recorte: Recorte) -> bool:
    """Aplica o corte temporal do recorte.

    O corte por `available_at` e o que impede o agente de explicar um incidente
    com dado que ainda nao teria chegado. O corte por janela e o que mantem o
    digest estavel entre execucoes.
    """
    if linha.available_at > recorte.sim_now:
        return False
    return recorte.janela_inicio <= linha.event_start <= recorte.janela_fim


def _buckets_vazios(instantes: list[dt.datetime]) -> int:
    """Conta os intervalos de 15 minutos sem ponto entre o primeiro e o ultimo."""
    if len(instantes) < 2:
        return 0
    passo = dt.timedelta(minutes=15)
    esperados = int((instantes[-1] - instantes[0]) / passo) + 1
    return max(0, esperados - len(set(instantes)))


def _media_por_hora(linhas: list[LinhaDeFato]) -> list[LinhaDeFato]:
    """Reduz a serie a uma linha por hora, preservando os fatos de origem.

    A linha agregada carrega em `fact_ids` todos os pontos que entraram na
    media. Sem isso, uma evidencia construida sobre a media nao poderia ser
    aberta na revisao.
    """
    por_hora: dict[dt.datetime, list[LinhaDeFato]] = {}
    for linha in linhas:
        hora = linha.event_start.replace(minute=0, second=0, microsecond=0)
        por_hora.setdefault(hora, []).append(linha)
    agregadas = []
    for hora, grupo in sorted(por_hora.items()):
        valores = [linha.value for linha in grupo if linha.value is not None]
        modelo = grupo[0]
        agregadas.append(
            LinhaDeFato(
                fact_id=f"agregado:{modelo.source}:{modelo.metric}:{hora.isoformat()}",
                source=modelo.source,
                entity=modelo.entity,
                metric=modelo.metric,
                event_start=hora,
                available_at=max(linha.available_at for linha in grupo),
                value=sum(valores) / len(valores) if valores else None,
                dimension_type=modelo.dimension_type,
                dimension_value=modelo.dimension_value,
                sample_size=len(grupo),
                kind=modelo.kind,
                fact_ids=tuple(linha.fact_id for linha in grupo),
            )
        )
    return agregadas
