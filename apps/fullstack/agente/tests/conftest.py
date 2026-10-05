"""Fixtures comuns: um recorte pequeno e atalhos para montar passos."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from argus_agente.casos import digest_do_conjunto
from argus_agente.contrato import Caso, Recorte
from argus_agente.ferramentas import FerramentasDeFixture

UTC = dt.UTC
INICIO = dt.datetime(2026, 8, 20, 17, 0, tzinfo=UTC)
SIM_NOW = dt.datetime(2026, 8, 20, 20, 15, tzinfo=UTC)


def ponto(
    minutos: int,
    valor: float,
    *,
    atraso: int = 60,
    metric: str = "http_5xx_rate",
    source: str = "prometheus",
    kind: str = "metric",
) -> dict[str, Any]:
    """Monta um fato de serie no bucket pedido."""
    instante = INICIO + dt.timedelta(minutes=minutos)
    return {
        "fact_id": f"{source}:{metric}:{minutos}",
        "source": source,
        "entity": "playback",
        "metric": metric,
        "event_start": instante.isoformat(),
        "available_at": (instante + dt.timedelta(seconds=atraso)).isoformat(),
        "value": valor,
        "kind": kind,
    }


@pytest.fixture
def recorte() -> Recorte:
    """Recorte de tres horas com presente simulado logo depois do fim."""
    return Recorte(
        checkpoint_id="ckpt-teste",
        sim_now=SIM_NOW,
        input_lsn=1000,
        janela_inicio=INICIO,
        janela_fim=INICIO + dt.timedelta(hours=3),
        digest="",
    )


@pytest.fixture
def fatos() -> list[dict[str, Any]]:
    """Uma serie estavel que sobe no fim, mais um deploy de contexto."""
    linhas = [ponto(15 * i, 0.4 if i < 8 else 7.0) for i in range(13)]
    linhas.append(
        {
            "fact_id": "deploy:playback:1",
            "source": "tsuru",
            "entity": "playback",
            "metric": "deploy",
            "event_start": (INICIO + dt.timedelta(minutes=114)).isoformat(),
            "available_at": (INICIO + dt.timedelta(minutes=116)).isoformat(),
            "value": 1.0,
            "kind": "context",
        }
    )
    return linhas


@pytest.fixture
def ferramentas(recorte: Recorte, fatos: list[dict[str, Any]]) -> FerramentasDeFixture:
    """Adaptador sobre os fatos da fixture."""
    return FerramentasDeFixture(recorte, fatos)


@pytest.fixture
def caso(recorte: Recorte, ferramentas: FerramentasDeFixture) -> Caso:
    """Caso montado sobre o recorte de teste, com digest calculado."""
    completo = Recorte(
        checkpoint_id=recorte.checkpoint_id,
        sim_now=recorte.sim_now,
        input_lsn=recorte.input_lsn,
        janela_inicio=recorte.janela_inicio,
        janela_fim=recorte.janela_fim,
        digest=digest_do_conjunto(ferramentas),
    )
    ferramentas.recorte = completo
    return Caso(
        case_id="caso-teste",
        recorte=completo,
        inventario=ferramentas.inventario(),
        lacunas_de_cobertura=ferramentas.lacunas_de_cobertura,
        nota_de_escopo="janela de 3 h",
    )


def consulta_serie(**extras: Any) -> dict[str, Any]:
    """Passo de consulta a serie que existe na fixture."""
    argumentos = {
        "source": "prometheus",
        "entity": "playback",
        "metric": "http_5xx_rate",
        "inicio": INICIO.isoformat(),
        "fim": (INICIO + dt.timedelta(hours=3)).isoformat(),
    }
    argumentos.update(extras)
    return {
        "action": "consultar",
        "rationale": "ver como o erro se comporta na janela",
        "tool": "serie",
        "arguments": argumentos,
    }


def conclusao(fact_ids: list[str], contra: list[str] | None = None) -> dict[str, Any]:
    """Passo de conclusao citando os fatos pedidos."""
    answer: dict[str, Any] = {
        "statement": "Possivel regressao apos deploy no playback",
        "scope": {"entity": "playback"},
        "evidence_for": [
            {
                "fact_ids": fact_ids,
                "observation": "a taxa de 5xx sobe de 0,4 para 7,0",
                "reading": "compativel com mudanca no servico",
            }
        ],
        "evidence_against": [],
        "gaps": [{"missing": "quebra por regiao", "reason": "ainda_indisponivel"}],
    }
    if contra:
        answer["evidence_against"] = [
            {
                "fact_ids": contra,
                "observation": "o volume total nao muda",
                "reading": "enfraquece a hipotese de queda de demanda",
            }
        ]
    return {"action": "concluir", "rationale": "evidencia reunida", "answer": answer}
