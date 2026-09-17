"""Testes unitários de controle de tamanho de payload em ``argus_worker.repository``.

Unidades testadas:
  - Função check_size: verificação estrita do limite de 4 MB (MAX_CHANGE_BYTES)
    e lançamento da exceção ChangeTooLarge.
"""

from __future__ import annotations

import pytest

from argus_worker.repository import MAX_CHANGE_BYTES, ChangeTooLarge, check_size


# ── TU-WRK-05 — check_size ─────────────────────────────────────────────────


class TestCheckSize:
    """Verifica a guarda de proteção contra payloads que poderiam corromper ou travar o TOAST do Postgres."""

    def test_deve_permitir_payload_com_tamanho_normal(self):
        """Payload com tamanho comum passa silenciosamente sem lançar exceção."""
        change = {
            "source_table": "signal_bucket",
            "op": "u",
            "pk": {"id": 1},
            "after": {"value": 123.45},
        }
        # Não deve levantar exceção
        check_size(change)

    def test_deve_rejeitar_payload_que_excede_limite_maximo(self):
        """Payload cujo JSON serializado ultrapassa 4.000.000 bytes deve levantar ChangeTooLarge."""
        dados_gigantes = "X" * (MAX_CHANGE_BYTES + 1024)
        change_grande = {
            "source_table": "operation_metrics",
            "op": "i",
            "pk": {"id": 1},
            "after": {"corpo": dados_gigantes},
        }

        with pytest.raises(ChangeTooLarge) as exc:
            check_size(change_grande)
        assert f"excede o limite de {MAX_CHANGE_BYTES}" in str(exc.value)

    def test_deve_permitir_payload_exatamente_no_limite(self):
        """Payload no limite exato não deve levantar exceção."""
        # Montamos um change cujo tamanho serializado fique ligeiramente abaixo de MAX_CHANGE_BYTES
        tamanho_desejado = MAX_CHANGE_BYTES - 200
        change_no_limite = {
            "source_table": "signal_bucket",
            "op": "i",
            "pk": {"id": 1},
            "after": {"dados": "A" * tamanho_desejado},
        }
        check_size(change_no_limite)
