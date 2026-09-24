"""Contrato do refinador textual de hipoteses publicadas."""

from typing import Any, Protocol


class HypothesisRefiner(Protocol):
    """Refina a apresentacao sem alterar a hipotese que serve de fonte."""

    def refine(self, hypothesis: dict[str, Any], *, question: str | None) -> dict[str, Any]:
        """Produz uma resposta rastreavel aos campos da hipotese.

        Args:
            hypothesis (dict[str, Any]): Hipotese publicada, com suas evidencias.
            question (str | None): Pergunta opcional do operador.

        Returns:
            dict[str, Any]: Resposta refinada e suas referencias de origem.
        """
