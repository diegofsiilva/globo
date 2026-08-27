"""O relogio virtual e a leitura da janela a frente dele.

O simulador nao inventa dado. Ele le o que ja esta na bronze -- os 26 dias do
dump da Globo -- e reemite como se estivesse acontecendo agora, no ritmo do
relogio virtual. E o que faz um dump estatico virar um fluxo sem que nada do que
chega seja ficcao.
"""

from __future__ import annotations

import datetime as dt
import logging

log = logging.getLogger(__name__)

# As tabelas que o simulador reemite, com a coluna de tempo de cada uma.
#
# Nao sao as 33. Reemitir `prom_point` (41 M linhas, cadencia de 1 min) faria o
# simulador sozinho gerar mais trafego do que o resto do sistema inteiro
# processa, e o valor dele nao esta no volume -- esta em mostrar o fluxo
# funcionando de ponta a ponta. As quatro escolhidas cobrem os dois grains
# (ponto e bucket), as fontes com latencia diferente e o calendario de
# transmissoes, que e o que as telas usam.
#
# Repare que a coluna de tempo tem nome diferente em cada uma: nao existe um
# `ts` universal neste dataset.
TABELAS = {
    "signal_bucket": "bts",
    "signal_point": "ts",
    "ca_point": "ts_ms",
    "rpaas_bucket": "bucket_ts_ms",
}


def para_ms(momento: dt.datetime) -> int:
    """Converte um instante para epoch em milissegundos.

    Args:
        momento (datetime): Instante com fuso.

    Returns:
        int: Epoch em milissegundos, que e a unidade de tempo do dataset.
    """
    return int(momento.timestamp() * 1000)


class Clock:
    """Le e avanca `sim.clock`."""

    def __init__(self, db) -> None:
        """Inicializa o relogio.

        Args:
            db (argus_common.Database): Pool de conexao.
        """
        self._db = db

    def reset(self, t0: dt.datetime, speed: float) -> None:
        """Posiciona o relogio no inicio da janela.

        Args:
            t0 (datetime): Instante virtual inicial.
            speed (float): Tempo virtual por segundo de parede.
        """
        # `%s::numeric` explicito: o psycopg manda float como `double
        # precision`, e o PostgreSQL nao converte sozinho para `numeric` na
        # hora de resolver qual funcao chamar -- o erro seria "function does
        # not exist", que manda procurar no lugar errado.
        self._db.fetch_one("SELECT sim.set_clock(%s, %s::numeric) AS agora", (t0, speed))
        log.info("relogio ancorado", extra={"sim_now": t0.isoformat(), "speed": speed})

    def now(self) -> dt.datetime:
        """Le o instante virtual.

        Returns:
            datetime: O presente virtual.
        """
        return self._db.sim_now()

    def abrir_run(self, seed: int, t0: dt.datetime, t1: dt.datetime, speed: float) -> int:
        """Registra uma execucao em `sim.run`.

        Args:
            seed (int): Semente da injecao de falhas.
            t0 (datetime): Inicio da janela.
            t1 (datetime): Fim da janela.
            speed (float): Velocidade do relogio.

        Returns:
            int: Identificador da execucao.
        """
        linha = self._db.fetch_one(
            """
            INSERT INTO sim.run (seed, t0, t1, speed, status)
            VALUES (%s, %s, %s, %s::numeric, 'running')
            RETURNING run_id
            """,
            (seed, t0, t1, speed),
        )
        return int(linha["run_id"])

    def registrar_falhas(self, run_id: int, falhas) -> None:
        """Grava as falhas sorteadas em `sim.fault`.

        Persistir e o que torna o cenario AUDITAVEL: sem isso, saber quais
        falhas o detector deveria ter pego exigiria reexecutar o sorteio de
        cabeca a partir da seed.

        Args:
            run_id (int): Execucao a que as falhas pertencem.
            falhas (list[Falha]): Falhas sorteadas.
        """
        if not falhas:
            return
        from psycopg.types.json import Jsonb

        with self._db.connection() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO sim.fault (run_id, kind, target, ts_start, ts_end, params)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        run_id,
                        f.kind,
                        Jsonb(f.target),
                        f.ts_start,
                        f.ts_end,
                        Jsonb(f.params),
                    )
                    for f in falhas
                ],
            )
        log.info("falhas registradas", extra={"run_id": run_id, "falhas": len(falhas)})

    def fechar_run(
        self,
        run_id: int,
        status: str = "done",
        momento: dt.datetime | None = None,
    ) -> None:
        """Marca o fim de uma execucao.

        Args:
            run_id (int): Execucao.
            status (str): Estado final.
            momento (datetime | None): Instante em que o relogio deve congelar.
                None preserva o sim.now() corrente.
        """
        self._db.fetch_one(
            "SELECT sim.close_run(%s, %s, %s) AS agora",
            (run_id, status, momento),
        )

    def fontes(self) -> list[str]:
        """Lista as fontes presentes na bronze.

        Returns:
            list[str]: Nomes das fontes, ordenados.
        """
        linhas = self._db.fetch_all(
            "SELECT DISTINCT source FROM bronze.signal_bucket ORDER BY source"
        )
        return [linha["source"] for linha in linhas]


class Janela:
    """Le da bronze as linhas cujo tempo caiu na janela que acabou de passar."""

    def __init__(self, db, limite_por_tabela: int = 5000) -> None:
        """Inicializa o leitor de janela.

        Args:
            db (argus_common.Database): Pool de conexao.
            limite_por_tabela (int): Teto de linhas por tabela por tick. Existe
                para que um tick longo (ou um `speed` alto) nao produza um lote
                grande demais para uma mensagem do SQS -- que tem limite de
                256 KB.
        """
        self._db = db
        self._limite = limite_por_tabela

    def ler(self, tabela: str, de: dt.datetime, ate: dt.datetime) -> list[dict]:
        """Le as linhas de uma tabela dentro de uma faixa de tempo.

        Args:
            tabela (str): Nome da tabela na bronze.
            de (datetime): Inicio da faixa (inclusivo).
            ate (datetime): Fim da faixa (exclusivo).

        Returns:
            list[dict]: Linhas encontradas, sem as colunas de controle.
        """
        coluna = TABELAS[tabela]
        # A coluna de tempo entra por interpolacao porque e IDENTIFICADOR, nao
        # valor -- bind nao funciona para nome de coluna. Seguro aqui porque a
        # unica origem possivel e a constante TABELAS acima, nunca entrada
        # externa.
        linhas = self._db.fetch_all(
            f"""
            SELECT * FROM bronze.{tabela}
             WHERE {coluna} >= %s AND {coluna} < %s
             ORDER BY {coluna}
             LIMIT %s
            """,
            (para_ms(de), para_ms(ate), self._limite),
        )
        return [
            {k: v for k, v in linha.items() if not k.startswith("_")} for linha in linhas
        ]
