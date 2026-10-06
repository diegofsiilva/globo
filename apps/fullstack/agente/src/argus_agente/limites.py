"""Tetos de execucao do piloto, aplicados pelo executor e nao pelo modelo.

A unica forma de parar a investigacao e uma guarda
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
    """Os tetos de um caso, em um unico objeto ajustavel.

    Os valores padrao estao descritos na arquitetura do
    agente. Mudar um deles e uma
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
    # Quantas vezes a MESMA chamada invalida pode falhar antes de o caso ser
    # encerrado. Uma chamada invalida isolada e dado; a mesma repetida depois do
    # erro ja devolvido e um loop -- dois modelos diferentes bateram na mesma
    # chamada invalida ate esgotar o teto de chamadas sem concluir.
    max_invalidas_iguais: int = 2

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
        if self.max_invalidas_iguais < 1:
            raise ValueError("max_invalidas_iguais precisa ser ao menos 1")


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
        self._invalidas_por_assinatura: dict[str, int] = {}

    def antes_do_passo(self) -> None:
        """Verifica tempo antes de pedir mais uma decisao ao modelo.

        Raises:
            TetoAtingido: Se o tempo de parede do caso acabou.
        """
        self.verificar_tempo()
        self.passos += 1

    def verificar_tempo(self) -> None:
        """Recusa uma resposta recebida depois do prazo do caso.

        Raises:
            TetoAtingido: Se o tempo de parede do caso acabou.
        """
        if self.decorrido >= self.orcamento.max_segundos:
            raise TetoAtingido("tempo")

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
        encerraria casos por uma regra que nao esta documentada.

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

    def registrar_chamada_invalida(self, assinatura: str) -> None:
        """Conta falhas identicas de ferramenta e corta o loop quando repetem.

        A primeira falha de uma chamada e dado: volta ao modelo como erro, com a
        chance de corrigir. A MESMA chamada repetida depois disso e um loop -- o
        modelo ignorou a correcao --, e o caso e encerrado em vez de gastar o teto
        de chamadas repetindo o mesmo erro.

        Args:
            assinatura (str): Identidade da consulta, sem os campos de paginacao,
                para que o mesmo pedido conte junto mesmo variando `limit`.

        Raises:
            TetoAtingido: Quando a mesma chamada invalida falhou vezes demais.
        """
        vistas = self._invalidas_por_assinatura.get(assinatura, 0) + 1
        self._invalidas_por_assinatura[assinatura] = vistas
        if vistas > self.orcamento.max_invalidas_iguais:
            raise TetoAtingido("repeticao_de_chamada_invalida")

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
