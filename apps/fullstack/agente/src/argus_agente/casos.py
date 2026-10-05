"""Carga de um caso reproduzivel a partir de um arquivo de fixture.

Enquanto o adaptador sobre `silver.analysis_fact_version` nao existe, o caso
vem de um arquivo. O formato e o mesmo em ambos os mundos: um recorte mais uma
lista de fatos ja normalizados. Trocar a origem e trocar a construcao de
`Ferramentas`, nao o ciclo do agente.

O digest e calculado aqui, sobre os fatos elegiveis depois do corte temporal.
Ele e o que torna a reexecucao comparavel: dois casos com o mesmo digest viram
o mesmo conjunto.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from argus_agente.contrato import Caso, Recorte
from argus_agente.ferramentas import FerramentasDeFixture


def carregar_caso(caminho: Path) -> tuple[Caso, FerramentasDeFixture]:
    """Le um arquivo de caso e devolve o caso montado e suas ferramentas.

    Args:
        caminho (Path): Arquivo JSON com `recorte` e `fatos`.

    Returns:
        tuple[Caso, FerramentasDeFixture]: Caso pronto e adaptador de consulta.

    Raises:
        ValueError: Se o arquivo nao tiver as chaves obrigatorias.
    """
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    for chave in ("case_id", "recorte", "fatos"):
        if chave not in dados:
            raise ValueError(f"{caminho.name}: falta a chave {chave!r}")
    bruto = dados["recorte"]
    recorte_sem_digest = Recorte(
        checkpoint_id=str(bruto["checkpoint_id"]),
        sim_now=dt.datetime.fromisoformat(bruto["sim_now"]),
        input_lsn=int(bruto["input_lsn"]),
        janela_inicio=dt.datetime.fromisoformat(bruto["janela_inicio"]),
        janela_fim=dt.datetime.fromisoformat(bruto["janela_fim"]),
        digest="",
    )
    ferramentas = FerramentasDeFixture(recorte_sem_digest, dados["fatos"])
    recorte = Recorte(
        checkpoint_id=recorte_sem_digest.checkpoint_id,
        sim_now=recorte_sem_digest.sim_now,
        input_lsn=recorte_sem_digest.input_lsn,
        janela_inicio=recorte_sem_digest.janela_inicio,
        janela_fim=recorte_sem_digest.janela_fim,
        digest=digest_do_conjunto(ferramentas),
    )
    ferramentas.recorte = recorte
    caso = Caso(
        case_id=str(dados["case_id"]),
        recorte=recorte,
        inventario=ferramentas.inventario(),
        lacunas_de_cobertura=ferramentas.lacunas_de_cobertura,
        nota_de_escopo=str(dados.get("nota_de_escopo", "")),
    )
    return caso, ferramentas


def digest_do_conjunto(ferramentas: FerramentasDeFixture) -> str:
    """Resume o conjunto elegivel em um identificador estavel.

    Args:
        ferramentas (FerramentasDeFixture): Adaptador ja filtrado pelo recorte.

    Returns:
        str: Prefixo do SHA-256 dos `fact_id` ordenados.
    """
    identificadores = sorted(linha.fact_id for linha in ferramentas.fatos)
    resumo = hashlib.sha256("\n".join(identificadores).encode()).hexdigest()
    return f"sha256:{resumo[:16]}"


def descrever_caso(caso: Caso) -> dict[str, Any]:
    """Resume um caso para o cabecalho de um relatorio.

    Args:
        caso (Caso): Caso carregado.

    Returns:
        dict[str, Any]: Campos curtos do recorte e tamanho do inventario.
    """
    return {
        "case_id": caso.case_id,
        "checkpoint_id": caso.recorte.checkpoint_id,
        "sim_now": caso.recorte.sim_now.isoformat(),
        "digest": caso.recorte.digest,
        "series": len(caso.inventario),
    }
