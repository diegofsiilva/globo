"""Despacho das tres ferramentas de leitura sobre o recorte.

O leitor que implementa as ferramentas e `leitor.py`. Este modulo nao
reimplementa consulta nenhuma: ele so escolhe o metodo pelo nome que o modelo
pediu e transforma a recusa do leitor em algo que o ciclo sabe registrar.

Essa fronteira existe porque as duas responsabilidades sao diferentes. O leitor
decide o que e visivel e recusa pedido fora do recorte -- corte temporal,
dimensao sem par, janela invertida. O ciclo decide o que fazer com a recusa: ela
consome uma chamada, entra no rastro e volta ao modelo como dado, em vez de
derrubar o caso.
"""

from __future__ import annotations

from typing import Any, Protocol


class FerramentaIndisponivel(ValueError):
    """O modelo pediu uma ferramenta que nao existe no contrato de leitura."""


class Ferramentas(Protocol):
    """As tres consultas de leitura, como o ciclo as enxerga.

    A assinatura e `**params` de proposito: quem valida nome e combinacao de
    argumentos e o `validador`, antes de chamar, e o proprio leitor, ao receber.
    Repetir a lista de parametros aqui criaria um terceiro lugar para ela
    divergir.
    """

    def inventariar_fatos(self, **params: Any) -> dict[str, Any]:
        """Lista as series do recorte, com cobertura e indicacao de nulos."""
        ...

    def consultar_serie(self, **params: Any) -> dict[str, Any]:
        """Devolve os pontos de uma metrica inventariada numa janela explicita."""
        ...

    def consultar_contexto(self, **params: Any) -> dict[str, Any]:
        """Devolve fatos de uma fonte ou entidade, incluindo eventos sobrepostos."""
        ...


def despachar(
    ferramentas: Ferramentas, nome: str, argumentos: dict[str, Any]
) -> dict[str, Any]:
    """Chama a ferramenta pedida e devolve o envelope do leitor.

    Args:
        ferramentas (Ferramentas): Leitor do recorte.
        nome (str): Nome da ferramenta, ja validado contra `FERRAMENTAS`.
        argumentos (dict[str, Any]): Argumentos aceitos pelo validador.

    Returns:
        dict[str, Any]: Envelope com `items`, `has_more`, `next_cursor` e
            `limitations`.

    Raises:
        FerramentaIndisponivel: Se o nome nao corresponder a uma ferramenta.
        ValueError: Repassado do leitor quando o pedido sai do recorte.
    """
    metodo = getattr(ferramentas, nome, None)
    if metodo is None or nome.startswith("_"):
        raise FerramentaIndisponivel(f"ferramenta desconhecida: {nome}")
    return metodo(**argumentos)


def fact_ids_de(envelope: dict[str, Any]) -> list[str]:
    """Extrai os identificadores citaveis de uma resposta de ferramenta.

    O inventario descreve series, nao observa nada: suas linhas nao tem
    `fact_id` e por isso nao podem virar evidencia. Sustentar uma causa na
    existencia da metrica, em vez de no valor dela, seria evidencia vazia.

    Args:
        envelope (dict[str, Any]): Resposta devolvida por uma ferramenta.

    Returns:
        list[str]: `fact_id` presentes nos itens, sem repeticao e em ordem.
    """
    vistos: dict[str, None] = {}
    for item in envelope.get("items", ()):
        fact_id = item.get("fact_id")
        if isinstance(fact_id, str):
            vistos.setdefault(fact_id, None)
    return list(vistos)
