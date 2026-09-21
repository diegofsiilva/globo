"""Testes unitários do particionamento de lotes em ``argus_simulator.emitter``.

Unidades testadas:
  - Função _blocos: algoritmo de fatiamento de lotes por limite de bytes
    (TETO_DO_CORPO_BYTES = 48 KB) e limite de itens (TETO_DE_ITENS = 500).
"""

from __future__ import annotations

import json

from argus_simulator.emitter import TETO_DE_ITENS, TETO_DO_CORPO_BYTES, _blocos

# ── TU-SIM-04 — _blocos ────────────────────────────────────────────────────


class TestEmitterBlocos:
    """Verifica a lógica de fragmentação de change events por tamanho e quantidade."""

    def test_deve_retornar_lista_vazia_quando_entrada_vazia(self):
        """Entrada vazia retorna lista vazia."""
        assert _blocos([]) == []

    def test_deve_manter_lote_unico_quando_abaixo_dos_limites(self):
        """Itens pequenos que somados não ultrapassam limites ficam no mesmo bloco."""
        changes = [
            {"source_table": "signal_bucket", "op": "u", "pk": {"id": i}, "value": 10.0}
            for i in range(10)
        ]
        blocos = _blocos(changes)

        assert len(blocos) == 1
        assert blocos[0] == changes

    def test_deve_fatiar_quando_exceder_teto_de_itens(self):
        """Ao atingir TETO_DE_ITENS (500), deve abrir um novo bloco."""
        changes = [
            {"source_table": "ca_point", "op": "i", "pk": {"id": i}} for i in range(1050)
        ]
        blocos = _blocos(changes)

        # 1050 itens -> 500 + 500 + 50 = 3 blocos
        assert len(blocos) == 3
        assert len(blocos[0]) == TETO_DE_ITENS
        assert len(blocos[1]) == TETO_DE_ITENS
        assert len(blocos[2]) == 50

        # Verifica preservação integral da ordem dos elementos
        concatenados = [item for bloco in blocos for item in bloco]
        assert concatenados == changes

    def test_deve_fatiar_quando_exceder_teto_de_bytes(self):
        """Ao ultrapassar TETO_DO_CORPO_BYTES (48 KB), corta o lote atual."""
        # Cada item com ~10 KB de payload
        payload_10k = "x" * 10_000
        changes = [
            {
                "source_table": "operation_metrics",
                "op": "i",
                "pk": {"id": i},
                "data": payload_10k,
            }
            for i in range(10)
        ]
        blocos = _blocos(changes)

        # 10 itens de 10 KB = ~100 KB -> precisa dividir em múltiplos blocos
        assert len(blocos) > 1

        for bloco in blocos:
            tamanho_bloco = sum(
                len(json.dumps(c, ensure_ascii=False, default=str).encode())
                for c in bloco
            )
            # A menos que seja um item isolado gigante, cada bloco respeita o teto
            if len(bloco) > 1:
                assert tamanho_bloco <= TETO_DO_CORPO_BYTES

    def test_item_individual_maior_que_teto_vai_em_bloco_isolado(self):
        """Um item que sozinho excede o teto deve ser emitido sozinho e não descartado."""
        item_gigante = {
            "source_table": "service_overview",
            "op": "i",
            "pk": {"id": 999},
            "payload_pesado": "A" * (TETO_DO_CORPO_BYTES + 5000),
        }
        item_normal_1 = {"source_table": "signal_bucket", "op": "u", "pk": {"id": 1}}
        item_normal_2 = {"source_table": "signal_bucket", "op": "u", "pk": {"id": 2}}

        changes = [item_normal_1, item_gigante, item_normal_2]
        blocos = _blocos(changes)

        # Deve gerar 3 blocos: [normal_1], [gigante], [normal_2]
        assert len(blocos) == 3
        assert blocos[0] == [item_normal_1]
        assert blocos[1] == [item_gigante]
        assert blocos[2] == [item_normal_2]
