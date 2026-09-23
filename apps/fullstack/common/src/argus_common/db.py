"""Acesso ao PostgreSQL: pool de conexao e o relogio virtual.

Um pool e nao uma conexao solta porque abrir conexao no PostgreSQL custa caro
(processo novo no servidor, nao thread), e um worker que reconecta a cada ciclo
gastaria mais tempo no handshake do que no trabalho. O pool tambem e o que faz o
worker sobreviver a um failover do RDS sem reiniciar: a conexao morta e
descartada e uma nova entra no lugar.
"""

from __future__ import annotations

import datetime as dt
import logging
import os

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)


class Database:
    """Pool de conexoes com o banco do Argus."""

    def __init__(
        self,
        url: str,
        *,
        min_size: int = 1,
        max_size: int = 4,
        application_name: str = "argus",
    ) -> None:
        """Abre o pool.

        Args:
            url (str): DSN no formato `postgresql://...`.
            min_size (int): Conexoes mantidas abertas mesmo ociosas.
            max_size (int): Teto de conexoes deste processo.
            application_name (str): Identificacao que aparece em
                `pg_stat_activity`. E o que permite descobrir QUAL servico
                esta segurando um lock, sem adivinhar pelo IP.
        """
        self._pool = ConnectionPool(
            conninfo=url,
            min_size=min_size,
            max_size=max_size,
            open=False,
            kwargs={"application_name": application_name, "autocommit": False},
            # Devolve conexao quebrada para o pool em vez de entrega-la ao
            # chamador: depois de um failover do RDS, as conexoes antigas ainda
            # parecem vivas ate a primeira query falhar.
            check=ConnectionPool.check_connection,
        )
        self._pool.open(wait=True, timeout=30)
        log.info("pool aberto", extra={"min_size": min_size, "max_size": max_size})

    @classmethod
    def from_env(cls, **kwargs) -> Database:
        """Constroi a partir de `DATABASE_URL`.

        Args:
            **kwargs: Repassados ao construtor.

        Returns:
            Database: Instancia com o pool aberto.

        Raises:
            RuntimeError: Se `DATABASE_URL` nao estiver definida.
        """
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL nao definida")
        return cls(url, **kwargs)

    def connection(self):
        """Empresta uma conexao do pool, devolvendo-a no fim do bloco `with`.

        Returns:
            Gerenciador de contexto que entrega uma `psycopg.Connection`. A
            transacao commita na saida limpa e faz rollback em excecao.
        """
        return self._pool.connection()

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Executa uma consulta e devolve todas as linhas como dicionario.

        Args:
            sql (str): Instrucao SQL.
            params (tuple): Parametros de bind.

        Returns:
            list[dict]: Linhas retornadas.
        """
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        """Executa uma consulta e devolve a primeira linha.

        Args:
            sql (str): Instrucao SQL.
            params (tuple): Parametros de bind.

        Returns:
            dict | None: Primeira linha, ou None se nao houver nenhuma.
        """
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def sim_now(self) -> dt.datetime:
        """Le o instante virtual do banco.

        O relogio vem do BANCO, nunca do relogio local do container. Se cada
        servico derivasse o proprio tempo virtual, dois containers discordariam
        sobre o que ja aconteceu -- e `available_at` deixaria de significar
        alguma coisa.

        Returns:
            datetime: O presente virtual.
        """
        row = self.fetch_one("SELECT sim.now() AS agora")
        return row["agora"]

    def healthy(self) -> bool:
        """Verifica se o banco responde.

        Returns:
            bool: True se a consulta trivial respondeu.
        """
        try:
            self.fetch_one("SELECT 1 AS ok")
        except psycopg.Error:
            log.warning("banco nao respondeu", exc_info=True)
            return False
        return True

    def close(self) -> None:
        """Fecha o pool."""
        self._pool.close()
