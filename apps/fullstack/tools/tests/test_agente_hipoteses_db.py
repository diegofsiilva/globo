"""Verifica barreiras de acesso do leitor operacional do agente."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agente_hipoteses_db import load_checkpoint


class DatabaseReaderGuardsTests(unittest.TestCase):
    """Recusa configurações que poderiam alcançar um banco fora do piloto."""

    def test_remote_host_is_rejected_before_connecting(self) -> None:
        """Uma URL remota não pode abrir conexão com dados publicados."""
        with self.assertRaisesRegex(ValueError, "apenas PostgreSQL local"):
            load_checkpoint("postgresql://user:password@example.com/db", 1, "player")

    def test_unbounded_recorte_is_rejected_before_connecting(self) -> None:
        """Entidade vazia e janela maior que um dia não iniciam leitura."""
        local = "postgresql://user:password@localhost/db"
        with self.assertRaisesRegex(ValueError, "obrigatórios"):
            load_checkpoint(local, 1, " ")
        with self.assertRaisesRegex(ValueError, "entre 1 e 1440"):
            load_checkpoint(local, 1, "player", lookback_minutes=1441)
