"""Tetos de execucao do piloto -- a parte do Dia 4 que o modelo nao controla.

O desenho do Dia 1 diz que a unica forma de parar a investigacao e uma guarda
fora do alcance do modelo. Por isso os contadores vivem aqui, no executor, e
nao em instrucao de prompt: um modelo que ignore o limite declarado no texto
continua sendo interrompido na proxima chamada.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from argus_agente.leitor import MAX_CHAMADAS, MAX_ITENS_POR_RESPOSTA


class TetoAtingido(RuntimeError):
    """A investigacao consumiu um dos limites e precisa terminar."""

    def __init__(self, motivo: str) -> None:
        """Guarda o limite que estourou, que vai para o registro do caso.

        Args:
            motivo (str): Nome curto do teto, usado no relatorio do lote.
        """
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True, slots=True)
class Orcamento:
    """Os tetos propostos no Dia 1, em um unico objeto ajustavel por caso.

    Os valores padrao sao os da secao 5.1 de
    `artefatos/arquitetura-agente-hipoteses-ia.md`. Mudar um deles e uma
    decisao que precisa aparecer no registro, e por isso o orcamento inteiro e
    gravado junto com o resultado.
    """

    # Os dois primeiros sao os mesmos tetos que o leitor aplica por dentro
    # (`MAX_CALLS` e `MAX_ITEMS`). Importa-los em vez de repetir o numero evita
    # que o executor prometa ao modelo um limite que o leitor nao honra.
    max_chamadas: int = MAX_CHAMADAS
    max_itens_por_resposta: int = MAX_ITENS_POR_RESPOSTA
    max_segundos: float = 300.0
    # Uma nova tentativa depois de uma resposta malformada. A segunda falha
    # separa "erro de formatacao" de "o modelo nao consegue responder".
    max_passos_invalidos: int = 1

    def __post_init__(self) -> None:
        """Recusa um orcamento que permitiria investigacao indefinida.

        Raises:
            ValueError: Se algum teto for nulo, negativo ou maior que o do leitor.
        """
        for campo in (self.max_chamadas, self.max_itens_por_resposta, self.max_segundos):
            if campo <= 0:
                raise ValueError("todo teto do orcamento precisa ser positivo")
        if self.max_itens_por_resposta > MAX_ITENS_POR_RESPOSTA:
            raise ValueError(
                f"o leitor nao devolve mais de {MAX_ITENS_POR_RESPOSTA} itens "
                "por resposta"
            )
        if self.max_chamadas > MAX_CHAMADAS:
            raise ValueError(f"o leitor nao aceita mais de {MAX_CHAMADAS} chamadas")
        if self.max_passos_invalidos < 0:
            raise ValueError("max_passos_invalidos nao pode ser negativo")


class Guardas:
    """Contadores de consumo de um caso, consultados antes de cada passo."""

    def __init__(
        self, orcamento: Orcamento, *, relogio: Callable[[], float] = time.monotonic
    ) -> None:
        """Inicia os contadores e marca o instante de partida.

        Args:
            orcamento (Orcamento): Tetos aplicados a este caso.
            relogio (Callable[[], float]): Fonte de tempo monotonico, injetavel
                para que os testes de teto nao precisem esperar de verdade.
        """
        self.orcamento = orcamento
        self._relogio = relogio
        self._inicio = relogio()
        self.chamadas = 0
        self.itens = 0
        self.passos = 0
        self.passos_invalidos = 0

    def antes_do_passo(self) -> None:
        """Verifica tempo antes de pedir mais uma decisao ao modelo.

        Raises:
            TetoAtingido: Se o tempo de parede do caso acabou.
        """
        if self.decorrido >= self.orcamento.max_segundos:
            raise TetoAtingido("tempo")
        self.passos += 1

    def antes_da_chamada(self) -> None:
        """Verifica o teto de chamadas de ferramenta.

        Raises:
            TetoAtingido: Se o numero de chamadas do caso se esgotou.
        """
        if self.chamadas >= self.orcamento.max_chamadas:
            raise TetoAtingido("chamadas")
        self.chamadas += 1

    def registrar_itens(self, quantidade: int) -> None:
        """Soma os itens lidos no caso, para o relatorio de consumo.

        Nao ha teto proprio aqui: o produto de `max_chamadas` por
        `max_itens_por_resposta` ja limita o total, e inventar um terceiro teto
        encerraria casos por uma regra que a secao 5.1 nao anuncia.

        Args:
            quantidade (int): Itens devolvidos pela ultima ferramenta.
        """
        self.itens += quantidade

    def registrar_passo_invalido(self) -> None:
        """Conta uma resposta malformada e decide se ainda cabe nova tentativa.

        Raises:
            TetoAtingido: Quando as tentativas permitidas acabaram.
        """
        self.passos_invalidos += 1
        if self.passos_invalidos > self.orcamento.max_passos_invalidos:
            raise TetoAtingido("respostas_invalidas")

    @property
    def decorrido(self) -> float:
        """Segundos de parede desde o inicio do caso."""
        return self._relogio() - self._inicio

    @property
    def consumo(self) -> dict[str, float | int]:
        """Resumo numerico para o registro do caso."""
        return {
            "chamadas": self.chamadas,
            "itens": self.itens,
            "passos": self.passos,
            "passos_invalidos": self.passos_invalidos,
            "segundos": round(self.decorrido, 3),
        }
