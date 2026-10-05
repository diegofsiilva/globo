"""O lote precisa sobreviver a um caso ruim e mostrar todos os desfechos."""

from __future__ import annotations

import json

from conftest import conclusao, consulta_serie

from argus_agente.lote import executar_lote
from argus_agente.modelo import ModeloDeRoteiro

TODOS = [f"prometheus:http_5xx_rate:{15 * i}" for i in range(13)]


def _instante(indice: int, segundos: str) -> str:
    """Monta o instante do bucket `indice` dentro da janela do caso."""
    hora, minuto = 17 + (15 * indice) // 60, (15 * indice) % 60
    return f"2026-08-20T{hora:02d}:{minuto:02d}:{segundos}+00:00"


def test_lote_grava_relatorio_e_nao_cai_com_caso_invalido(tmp_path):
    bom = tmp_path / "caso-bom.json"
    bom.write_text(
        json.dumps(
            {
                "case_id": "caso-bom",
                "recorte": {
                    "checkpoint_id": "ckpt",
                    "sim_now": "2026-08-20T20:15:00+00:00",
                    "input_lsn": 10,
                    "janela_inicio": "2026-08-20T17:00:00+00:00",
                    "janela_fim": "2026-08-20T20:00:00+00:00",
                },
                "fatos": [
                    {
                        "fact_id": f"prometheus:http_5xx_rate:{15 * i}",
                        "source": "prometheus",
                        "entity": "playback",
                        "metric": "http_5xx_rate",
                        "event_start": _instante(i, "00"),
                        "available_at": _instante(i, "30"),
                        "value": 0.4 if i < 8 else 7.0,
                        "kind": "metric",
                    }
                    for i in range(13)
                ],
            }
        ),
        encoding="utf-8",
    )
    ruim = tmp_path / "caso-ruim.json"
    ruim.write_text(json.dumps({"case_id": "caso-ruim"}), encoding="utf-8")

    registros = executar_lote(
        [bom, ruim],
        lambda _case_id: ModeloDeRoteiro([consulta_serie(), conclusao(TODOS[:3])]),
        destino=tmp_path / "saida",
    )

    assert [registro.desfecho for registro in registros] == [
        "hipotese",
        "erro_de_execucao",
    ]
    relatorio = (tmp_path / "saida" / "relatorio.md").read_text(encoding="utf-8")
    assert "caso-bom" in relatorio and "erro de execucao" in relatorio
    assert (tmp_path / "saida" / "casos" / "caso-bom.json").exists()
