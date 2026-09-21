"""Testes unitários de controle de tamanho de payload em ``argus_worker.repository``.

Unidades testadas:
  - Função check_size: verificação estrita do limite de 4 MB (MAX_CHANGE_BYTES)
    e lançamento da exceção ChangeTooLarge.
"""

from __future__ import annotations

import json

import pytest

from argus_worker.repository import MAX_CHANGE_BYTES, ChangeTooLarge, check_size

# ── TU-WRK-05 — check_size ─────────────────────────────────────────────────


class TestCheckSize:
    """Verifica a guarda contra payloads grandes demais para o PostgreSQL."""

    @staticmethod
    def _change_com_tamanho_serializado(tamanho: int) -> dict:
        """Monta um change cujo JSON serializado tem o tamanho solicitado."""
        change = {
            "source_table": "signal_bucket",
            "op": "i",
            "pk": {"id": 1},
            "after": {"dados": ""},
        }
        tamanho_fixo = len(json.dumps(change).encode("utf-8"))
        change["after"]["dados"] = "A" * (tamanho - tamanho_fixo)
        assert len(json.dumps(change).encode("utf-8")) == tamanho
        return change

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
        """Rejeita o JSON serializado que ultrapassa o limite máximo."""
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
        change_no_limite = self._change_com_tamanho_serializado(MAX_CHANGE_BYTES)
        check_size(change_no_limite)

    def test_deve_rejeitar_payload_um_byte_acima_do_limite(self):
        """Payload um byte acima do limite levanta ChangeTooLarge."""
        change_acima = self._change_com_tamanho_serializado(MAX_CHANGE_BYTES + 1)

        with pytest.raises(ChangeTooLarge):
            check_size(change_acima)
