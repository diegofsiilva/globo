"""Fixtures comuns: um recorte pequeno no formato do leitor e atalhos de passo."""

from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any

import pytest

from argus_agente.contrato import Caso, Recorte
from argus_agente.leitor import CaseReader

UTC = dt.UTC
INICIO = dt.datetime(2026, 8, 20, 17, 0, tzinfo=UTC)
SIM_NOW = dt.datetime(2026, 8, 20, 20, 15, tzinfo=UTC)
FIM_JANELA = INICIO + dt.timedelta(hours=3)


def _chave(*partes: Any) -> str:
    """Monta uma `fact_key` de 64 caracteres, como o leitor exige."""
    corpo = "\x1f".join(str(parte) for parte in partes)
    return hashlib.sha256(corpo.encode()).hexdigest()


def iso(instante: dt.datetime) -> str:
    """Formata um instante como o contrato espera."""
    return instante.isoformat().replace("+00:00", "Z")


def fato(
    lsn: int,
    source: str,
    metric: str,
    quando: dt.datetime,
    valor: float | None,
    *,
    atraso: int = 60,
    kind: str = "metric",
    role: str = "context",
    fim: dt.datetime | None = None,
    apagado: bool = False,
    chave: str | None = None,
) -> dict[str, Any]:
    """Monta uma versao de fato no formato do leitor."""
    return {
        "fact_key": chave or _chave(source, metric, iso(quando)),
        "version_lsn": lsn,
        "role": role,
        "kind": kind,
        "event_start": iso(quando),
        "event_end": iso(fim) if fim else None,
        "available_at": iso(quando + dt.timedelta(seconds=atraso)),
        "source": source,
        "entity": "playback",
        "metric": metric,
        "dimension_type": None,
        "dimension_value": None,
        "value": valor,
        "sample_size": None,
        "attributes": {},
        "is_deleted": apagado,
    }


@pytest.fixture
def fatos() -> list[dict[str, Any]]:
    """Uma serie que sobe no fim, mais um deploy de contexto."""
    linhas = [
        fato(
            1000 + i,
            "prometheus",
            "http_5xx_rate",
            INICIO + dt.timedelta(minutes=15 * i),
            0.4 if i < 8 else 7.0,
            role="subject",
        )
        for i in range(13)
    ]
    linhas.append(
        fato(
            1100,
            "tsuru",
            "deploy",
            INICIO + dt.timedelta(minutes=114),
            1.0,
            atraso=120,
            kind="context",
            fim=INICIO + dt.timedelta(minutes=118),
        )
    )
    return linhas


@pytest.fixture
def caso_bruto(fatos: list[dict[str, Any]]) -> dict[str, Any]:
    """O arquivo de caso, antes de virar `CaseReader`."""
    return {
        "case_id": "caso-teste",
        "origin": "synthetic",
        "checkpoint_id": 999,
        "sim_now": iso(SIM_NOW),
        "input_lsn": 2000,
        "nota_de_escopo": "janela de 3 h",
        "facts": fatos,
    }


@pytest.fixture
def ferramentas(caso_bruto: dict[str, Any]) -> CaseReader:
    """Leitor do recorte de teste."""
    return CaseReader(caso_bruto)


@pytest.fixture
def caso(ferramentas: CaseReader, caso_bruto: dict[str, Any]) -> Caso:
    """Caso montado sobre o recorte de teste."""
    return Caso(
        case_id=ferramentas.case_id,
        recorte=Recorte(
            checkpoint_id=str(caso_bruto["checkpoint_id"]),
            origin=ferramentas.origin,
            sim_now=ferramentas.sim_now,
            input_lsn=ferramentas.input_lsn,
            recorte_id=ferramentas.recorte_id,
            digest=ferramentas.digest,
        ),
        inventario=ferramentas.inventariar_fatos(),
        nota_de_escopo=str(caso_bruto["nota_de_escopo"]),
    )


def fact_ids_da_serie(leitor: CaseReader) -> list[str]:
    """Identificadores da serie de erro, na ordem em que o leitor os devolve."""
    resposta = leitor.consultar_serie(
        source="prometheus",
        entity="playback",
        metric="http_5xx_rate",
        inicio=iso(INICIO),
        fim=iso(FIM_JANELA),
    )
    return [item["fact_id"] for item in resposta["items"]]


def consulta_serie(**extras: Any) -> dict[str, Any]:
    """Passo de consulta a serie que existe na fixture."""
    argumentos: dict[str, Any] = {
        "source": "prometheus",
        "entity": "playback",
        "metric": "http_5xx_rate",
        "inicio": iso(INICIO),
        "fim": iso(FIM_JANELA),
    }
    argumentos.update(extras)
    return {
        "action": "consultar",
        "rationale": "ver como o erro se comporta na janela",
        "tool": "consultar_serie",
        "arguments": argumentos,
    }


def conclusao(fact_ids: list[str], contra: list[str] | None = None) -> dict[str, Any]:
    """Passo de conclusao completo: evidencia a favor, refutacao e rivais.

    Por padrao a refutacao cita o ultimo fato pedido e as duas alternativas
    citam fatos reais, para que o passo passe no validador. Um teste que quer
    justamente a falta de refutacao zera `evidence_against` depois.
    """
    refutacao = contra if contra else fact_ids[-1:]
    answer: dict[str, Any] = {
        "statement": "Possivel regressao apos deploy no playback, a partir das 19h",
        "scope": {"entity": "playback"},
        "effect_start": "2026-08-20T19:00:00Z",
        "evidence_for": [
            {
                "fact_ids": fact_ids,
                "observation": "a taxa de 5xx sobe de 0,4 para 7,0",
                "reading": "compativel com mudanca no servico",
            }
        ],
        "evidence_against": [
            {
                "fact_ids": refutacao,
                "observation": "o bucket final ainda nao confirma a mudanca",
                "reading": "enfraquece a hipotese, sem afirmar direcao",
            }
        ],
        "alternativas": [
            {
                "explicacao": "regressao apos deploy",
                "veredito": "sustentada",
                "fact_ids": fact_ids[:1],
                "observation": "o degrau coincide com o deploy",
            },
            {
                "explicacao": "queda de demanda",
                "veredito": "refutada",
                "fact_ids": refutacao,
                "observation": "o volume nao cai",
            },
        ],
        "gaps": [{"missing": "quebra por regiao", "reason": "ainda_indisponivel"}],
    }
    if contra:
        answer["evidence_against"][0]["fact_ids"] = contra
    return {"action": "concluir", "rationale": "evidencia reunida", "answer": answer}
