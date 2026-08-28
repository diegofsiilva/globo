"""Reducao das raias da tela Timeline (rotas-frontend.md §4.4.6).

A rota `/api/v1/timeline` devolvia a janela inteira ponto a ponto, o que chegou
a 562 KB em pouco mais de 5 s -- fora do orcamento do RNF02, e sem que a tela
tivesse onde desenhar tanto ponto: uma raia de 3 h nao tem 3.000 pixels de
largura.

Este modulo concentra o teto e a regra de reducao. Fica na camada de aplicacao,
e nao em `interfaces/http.py`, por dois motivos: a decisao e de dominio (o que
significa "reduzir sem mentir sobre a janela") e `interfaces/openapi.py` precisa
importar a constante para documenta-la -- importar de `http.py` fecharia um
ciclo, ja que e `http.py` quem importa a spec.
"""

from __future__ import annotations

from typing import Any

# Teto de entradas por raia.
LIMITE_POR_RAIA = 100


def amostrar_raia(
    pontos: list[dict[str, Any]], limite: int = LIMITE_POR_RAIA
) -> tuple[list[dict[str, Any]], bool]:
    """Reduz uma raia de serie a `limite` pontos sem encolher a janela.

    Amostra em passo uniforme sobre a lista ja ordenada por tempo, em vez de
    cortar o excedente. Cortar devolveria uma raia que cobre so o comeco da
    janela pedida, e o grafico mostraria uma lacuna onde na verdade ha dado --
    um erro de leitura pior que a perda de resolucao. O primeiro e o ultimo
    ponto sao sempre preservados, para que a raia continue encostando nas
    bordas do periodo.

    A regra vale para raia de SERIE. Deploy e incidente sao eventos discretos:
    amostrar omitiria incidentes reais no meio da janela, entao aqueles sao
    truncados em ordem cronologica e sinalizam `truncated`.

    Args:
        pontos (list[dict[str, Any]]): Pontos da raia, ordenados por
            `bucket_ts`.
        limite (int): Quantos pontos devolver no maximo.

    Returns:
        tuple[list[dict[str, Any]], bool]: Os pontos a devolver e se houve
            reducao.
    """
    total = len(pontos)
    if total <= limite:
        return pontos, False
    passo = (total - 1) / (limite - 1)
    # `set` porque dois indices podem arredondar para o mesmo ponto; nesse caso
    # a raia sai com um ponto a menos, o que e preferivel a duplicar um instante
    # e desenhar dois marcadores sobrepostos.
    indices = sorted({round(i * passo) for i in range(limite)})
    return [pontos[i] for i in indices], True
