"""Execucao de varios casos em sequencia -- a entrega do Dia 5.

Um lote e uma lista de casos investigados com o mesmo modelo, o mesmo prompt e
o mesmo orcamento. Um caso que falha nao derruba o lote: ele vira um registro
com desfecho de erro e aparece no relatorio, porque um lote que esconde as
falhas nao serve para decidir se o piloto continua.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from argus_agente.agente import investigar
from argus_agente.casos import carregar_caso
from argus_agente.contrato import DESFECHO_ERRO, RegistroDoCaso
from argus_agente.limites import Orcamento
from argus_agente.registro import escrever_lote

log = logging.getLogger(__name__)


def executar_lote(
    caminhos: Iterable[Path],
    fabrica_modelo: Callable[[str], Any],
    *,
    destino: Path,
    orcamento: Orcamento | None = None,
) -> list[RegistroDoCaso]:
    """Investiga todos os casos e grava o lote.

    Args:
        caminhos (Iterable[Path]): Arquivos de caso.
        fabrica_modelo (Callable[[str], Any]): Cria um modelo para o caso cujo
            identificador recebe. E uma fabrica, e nao um modelo pronto, para
            que um dublê de roteiro possa comecar do zero em cada caso.
        destino (Path): Diretorio do lote.
        orcamento (Orcamento | None): Tetos aplicados a todos os casos.

    Returns:
        list[RegistroDoCaso]: Registros na ordem de execucao.
    """
    registros: list[RegistroDoCaso] = []
    for caminho in sorted(caminhos):
        registros.append(_um_caso(caminho, fabrica_modelo, orcamento))
    escrever_lote(registros, destino)
    return registros


def _um_caso(
    caminho: Path, fabrica_modelo: Callable[[str], Any], orcamento: Orcamento | None
) -> RegistroDoCaso:
    """Investiga um caso e converte qualquer falha em registro de erro."""
    try:
        caso, ferramentas = carregar_caso(caminho)
    except (OSError, ValueError) as erro:
        log.warning("caso %s nao pode ser carregado: %s", caminho.name, erro)
        return RegistroDoCaso(
            case_id=caminho.stem,
            desfecho=DESFECHO_ERRO,
            motivo=f"caso invalido: {erro}",
        )
    try:
        return investigar(
            caso, ferramentas, fabrica_modelo(caso.case_id), orcamento=orcamento
        )
    except Exception as erro:  # noqa: BLE001 - um caso nao pode derrubar o lote
        log.exception("caso %s falhou", caso.case_id)
        return RegistroDoCaso(
            case_id=caso.case_id,
            desfecho=DESFECHO_ERRO,
            motivo=f"{type(erro).__name__}: {erro}"[:200],
        )
