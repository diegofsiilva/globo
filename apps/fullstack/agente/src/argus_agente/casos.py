"""Carga de um caso reproduzivel no formato do leitor de fatos.

Um caso e um arquivo JSON com a identidade do checkpoint e a lista de versoes
de fato. O mesmo formato vale para recorte sintetico e para recorte extraido do
banco: muda a origem, nao a estrutura. E o `CaseReader` que decide o que e
visivel, calcula o digest e monta o `recorte_id` -- aqui so se le o arquivo e se
embrulha o resultado nos tipos do piloto.

O campo `queries`, quando existe, e ignorado. Ele serve ao executor sintetico de
`tools/`, que repete consultas declaradas; no piloto quem escolhe as consultas e
o agente.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from argus_agente.contrato import Caso, Recorte
from argus_agente.leitor import CaseReader

CAMPOS_OBRIGATORIOS = (
    "case_id",
    "origin",
    "checkpoint_id",
    "sim_now",
    "input_lsn",
    "facts",
)


def carregar_caso(caminho: Path) -> tuple[Caso, CaseReader]:
    """Le um arquivo de caso e devolve o caso montado e seu leitor.

    Args:
        caminho (Path): Arquivo JSON no formato do leitor de fatos.

    Returns:
        tuple[Caso, CaseReader]: Caso pronto e leitor do recorte.

    Raises:
        ValueError: Se faltar campo obrigatorio ou o recorte for invalido.
    """
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    faltando = [campo for campo in CAMPOS_OBRIGATORIOS if campo not in dados]
    if faltando:
        raise ValueError(f"{caminho.name}: faltam os campos {faltando}")
    leitor = CaseReader(dados)
    recorte = Recorte(
        checkpoint_id=str(dados["checkpoint_id"]),
        origin=leitor.origin,
        sim_now=leitor.sim_now,
        input_lsn=leitor.input_lsn,
        recorte_id=leitor.recorte_id,
        digest=leitor.digest,
    )
    caso = Caso(
        case_id=leitor.case_id,
        recorte=recorte,
        inventario=leitor.inventariar_fatos(),
        nota_de_escopo=str(dados.get("nota_de_escopo", "")),
    )
    return caso, leitor


def descrever_caso(caso: Caso) -> dict[str, Any]:
    """Resume um caso para o cabecalho de um relatorio ou log.

    Args:
        caso (Caso): Caso carregado.

    Returns:
        dict[str, Any]: Campos curtos do recorte e tamanho do inventario.
    """
    return {
        "case_id": caso.case_id,
        "recorte_id": caso.recorte.recorte_id,
        "sim_now": caso.recorte.sim_now.isoformat(),
        "digest": caso.recorte.digest[:16],
        "series": caso.inventario["returned"],
    }


def janela_do_inventario(caso: Caso) -> tuple[dt.datetime | None, dt.datetime | None]:
    """Deduz o alcance observavel do recorte a partir do inventario.

    O recorte nao carrega uma janela propria: o limite superior e o `sim_now` e
    o inferior e simplesmente o fato mais antigo que sobreviveu ao corte. Dizer
    isso ao agente evita que ele peca periodos onde nao existe observacao
    alguma e gaste chamada com resposta vazia.

    Args:
        caso (Caso): Caso carregado.

    Returns:
        tuple[dt.datetime | None, dt.datetime | None]: Primeiro e ultimo
            instante de evento presentes no inventario, ou `None` se vazio.
    """
    itens = caso.inventario.get("items", ())
    if not itens:
        return None, None
    inicios = [dt.datetime.fromisoformat(item["event_start_min"]) for item in itens]
    fins = [dt.datetime.fromisoformat(item["event_start_max"]) for item in itens]
    return min(inicios), max(fins)
