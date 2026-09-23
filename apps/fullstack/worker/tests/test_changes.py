"""Testes unitários de validação e coerência de esquemas em ``argus_worker.changes``.

Unidades testadas:
  - Classe ChangeEvent:
      - Validador _tabela_conhecida: controle fechado de tabelas de origem
      - Validador _para_utc: garantia de fuso horário UTC em timestamps
      - Validador _pk_nao_vazia: garantia de chave primária identificável para o MERGE
  - Função parse_change:
      - Regra de coerência entre operação ('i', 'u', 'r') e obrigatoriedade de 'after'
"""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from argus_worker.changes import ChangeEvent, parse_change

# ── TU-WRK-04 — ChangeEvent e parse_change ─────────────────────────────────


class TestChangeEventValidation:
    """Verifica as regras de validação declaradas no modelo ChangeEvent."""

    def test_deve_aceitar_change_event_valido(self):
        """Caso válido: tabela conhecida, op coerente, pk preenchida, after presente."""
        raw = {
            "source_table": "signal_bucket",
            "op": "u",
            "pk": {"bts": 1784904300000, "source": "prometheus"},
            "before": {"value": 10.0},
            "after": {"value": 20.0},
            "captured_at": "2026-07-24T12:00:00Z",
        }
        change = parse_change(raw)

        assert change["source_table"] == "signal_bucket"
        assert change["op"] == "u"
        assert change["pk"] == {"bts": 1784904300000, "source": "prometheus"}
        assert change["after"]["value"] == 20.0
        assert change["captured_at"].tzinfo == dt.UTC

    def test_deve_rejeitar_tabela_desconhecida(self):
        """Validador _tabela_conhecida: tabela não catalogada levanta ValidationError."""
        raw = {
            "source_table": "tabela_inexistente_xpto",
            "op": "i",
            "pk": {"id": 1},
            "after": {"val": 100},
            "captured_at": "2026-07-24T12:00:00Z",
        }
        with pytest.raises(ValidationError) as exc:
            parse_change(raw)
        assert "tabela desconhecida" in str(exc.value)

    def test_deve_converter_timestamp_naive_para_utc(self):
        """Validador _para_utc: data sem fuso horário informado ganha dt.UTC."""
        evento = ChangeEvent(
            source_table="signal_bucket",
            op="i",
            pk={"id": 1},
            after={"ok": True},
            captured_at=dt.datetime(2026, 8, 1, 15, 30, 0),  # sem tzinfo
        )
        assert evento.captured_at.tzinfo == dt.UTC
        assert evento.captured_at.hour == 15

    def test_deve_converter_timestamp_com_fuso_para_utc(self):
        """Converte para UTC uma data informada em outro fuso."""
        fuso_br = dt.timezone(dt.timedelta(hours=-3))
        evento = ChangeEvent(
            source_table="signal_bucket",
            op="i",
            pk={"id": 1},
            after={"ok": True},
            captured_at=dt.datetime(2026, 8, 1, 15, 30, 0, tzinfo=fuso_br),
        )
        assert evento.captured_at.tzinfo == dt.UTC
        assert evento.captured_at.hour == 18  # 15h em UTC-3 = 18h em UTC

    def test_deve_rejeitar_pk_vazia(self):
        """Validador _pk_nao_vazia: pk vazia {} levanta ValidationError."""
        raw = {
            "source_table": "live_event",
            "op": "i",
            "pk": {},
            "after": {"evento": "gol"},
            "captured_at": "2026-07-24T12:00:00Z",
        }
        with pytest.raises(ValidationError) as exc:
            parse_change(raw)
        assert "pk vazia" in str(exc.value)

    def test_deve_rejeitar_insert_update_e_read_sem_after(self):
        """Exige ``after`` não vazio para as operações ``i``, ``u`` e ``r``."""
        for op in ("i", "u", "r"):
            raw_sem_after = {
                "source_table": "live_event",
                "op": op,
                "pk": {"id": 123},
                "after": None,
                "captured_at": "2026-07-24T12:00:00Z",
            }
            with pytest.raises(ValueError, match=f"op='{op}' exige `after`"):
                parse_change(raw_sem_after)

            raw_after_vazio = {
                "source_table": "live_event",
                "op": op,
                "pk": {"id": 123},
                "after": {},
                "captured_at": "2026-07-24T12:00:00Z",
            }
            with pytest.raises(ValueError, match=f"op='{op}' exige `after`"):
                parse_change(raw_after_vazio)

    def test_deve_permitir_delete_sem_after(self):
        """Operação de delete ('d') é válida mesmo sem o campo 'after'."""
        raw_delete = {
            "source_table": "live_event",
            "op": "d",
            "pk": {"id": 123},
            "before": {"status": "antigo"},
            "after": None,
            "captured_at": "2026-07-24T12:00:00Z",
        }
        change = parse_change(raw_delete)
        assert change["op"] == "d"
        assert change["after"] is None
