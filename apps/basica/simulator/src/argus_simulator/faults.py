"""Injecao de falhas deterministica.

A `seed` de `sim.run` e o que torna o cenario reproduzivel: duas execucoes com a
mesma seed produzem exatamente a mesma sequencia de falhas, nos mesmos
instantes, sobre os mesmos alvos. E isso que permite comparar dois detectores e
saber que a diferenca veio do detector, e nao de terem visto incidentes
diferentes.

Todo o sorteio passa por `random.Random(seed)` -- nunca pelo `random` global, e
nunca por `datetime.now()`. Um unico uso do gerador global em qualquer ponto do
processo quebraria a reprodutibilidade de um jeito quase impossivel de depurar.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass

# As falhas que o simulador sabe injetar. Cada uma distorce o valor de um jeito
# diferente porque um detector que so reconhece "valor sobe" seria facil demais.
TIPOS = ("error_spike", "latency", "source_outage", "drift")


@dataclass(frozen=True)
class Falha:
    """Uma falha injetada, com alvo e janela."""

    kind: str
    target: dict
    ts_start: dt.datetime
    ts_end: dt.datetime
    params: dict

    def alcanca(self, ts: dt.datetime, source: str, entity: str, metric: str) -> bool:
        """Diz se esta falha afeta o ponto informado.

        Args:
            ts (datetime): Instante do ponto.
            source (str): Fonte do ponto.
            entity (str): Entidade do ponto.
            metric (str): Metrica do ponto.

        Returns:
            bool: True se o ponto cai na janela e casa com o alvo.
        """
        if not (self.ts_start <= ts < self.ts_end):
            return False
        # Alvo ausente significa "qualquer valor": e o que permite uma falha
        # atingir a fonte inteira sem ter que enumerar as entidades dela.
        for chave, valor in (("source", source), ("entity", entity), ("metric", metric)):
            esperado = self.target.get(chave)
            if esperado is not None and esperado != valor:
                return False
        return True

    def aplicar(self, valor: float | None) -> float | None:
        """Distorce o valor conforme o tipo da falha.

        Args:
            valor (float | None): Valor original.

        Returns:
            float | None: Valor distorcido. `source_outage` devolve None -- a
                fonte parou de reportar, que e diferente de reportar zero. Zero
                seria um dado; None e um buraco, e sao coisas que o detector
                precisa distinguir.
        """
        if valor is None:
            return None
        if self.kind == "source_outage":
            return None
        return valor * float(self.params.get("multiplicador", 1.0))


def sortear(
    seed: int,
    t0: dt.datetime,
    t1: dt.datetime,
    fontes: list[str],
    quantas: int = 6,
) -> list[Falha]:
    """Sorteia as falhas de uma execucao, de forma deterministica.

    Args:
        seed (int): Semente. Mesma seed, mesmo cenario.
        t0 (datetime): Inicio da janela simulada.
        t1 (datetime): Fim da janela simulada.
        fontes (list[str]): Fontes candidatas a receber falha.
        quantas (int): Quantas falhas injetar na janela.

    Returns:
        list[Falha]: Falhas ordenadas por inicio.
    """
    rng = random.Random(seed)
    # Ordena as fontes antes de sortear: `fontes` chega de um SELECT, e a ordem
    # de um SELECT sem ORDER BY nao e estavel. Sem isto a mesma seed daria
    # cenarios diferentes conforme o plano de execucao do PostgreSQL.
    fontes = sorted(fontes)
    if not fontes:
        return []

    duracao = (t1 - t0).total_seconds()
    falhas: list[Falha] = []

    for _ in range(quantas):
        kind = rng.choice(TIPOS)
        inicio = t0 + dt.timedelta(seconds=rng.uniform(0, max(duracao - 3600, 1)))
        minutos = rng.choice([15, 30, 45, 60, 90])

        falhas.append(
            Falha(
                kind=kind,
                target={"source": rng.choice(fontes)},
                ts_start=inicio,
                ts_end=inicio + dt.timedelta(minutes=minutos),
                params=_params(kind, rng),
            )
        )

    return sorted(falhas, key=lambda f: f.ts_start)


def _params(kind: str, rng: random.Random) -> dict:
    """Parametros da distorcao, por tipo de falha.

    Args:
        kind (str): Tipo da falha.
        rng (random.Random): Gerador semeado.

    Returns:
        dict: Parametros da falha.
    """
    if kind == "error_spike":
        # Salto grande e obvio: e o incidente que o detector TEM que pegar.
        return {"multiplicador": rng.uniform(3.0, 12.0)}
    if kind == "latency":
        # Degradacao sutil. Fica dentro do que a variacao diaria normal alcanca,
        # entao separa o detector que modela o ciclo circadiano do que so olha
        # um limiar fixo.
        return {"multiplicador": rng.uniform(1.15, 1.6)}
    if kind == "drift":
        return {"multiplicador": rng.uniform(0.7, 0.9)}
    return {}  # source_outage nao precisa de parametro: o valor some
