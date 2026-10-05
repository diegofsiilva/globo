"""O lote precisa sobreviver a um caso ruim e mostrar todos os desfechos."""

from __future__ import annotations

import json

from conftest import conclusao, consulta_serie

from argus_agente.casos import carregar_caso
from argus_agente.lote import executar_lote
from argus_agente.modelo import ModeloDeRoteiro


def test_lote_grava_relatorio_e_nao_cai_com_caso_invalido(
    tmp_path, caso_bruto, ferramentas
):
    bom = tmp_path / "caso-bom.json"
    bom.write_text(json.dumps(caso_bruto), encoding="utf-8")
    ruim = tmp_path / "caso-ruim.json"
    ruim.write_text(json.dumps({"case_id": "caso-ruim"}), encoding="utf-8")

    _, leitor = carregar_caso(bom)
    serie = leitor.consultar_serie(
        source="prometheus",
        entity="playback",
        metric="http_5xx_rate",
        inicio=caso_bruto["facts"][0]["event_start"],
        fim=caso_bruto["facts"][12]["event_start"],
    )
    citaveis = [item["fact_id"] for item in serie["items"]][:3]

    registros = executar_lote(
        [bom, ruim],
        lambda _case_id: ModeloDeRoteiro([consulta_serie(), conclusao(citaveis)]),
        destino=tmp_path / "saida",
    )

    assert [registro.desfecho for registro in registros] == [
        "hipotese",
        "erro_de_execucao",
    ]
    assert [registro.util for registro in registros] == [True, False]
    relatorio = (tmp_path / "saida" / "relatorio.md").read_text(encoding="utf-8")
    assert "caso-teste" in relatorio and "erro de execucao" in relatorio
    assert (tmp_path / "saida" / "casos" / "caso-teste.json").exists()
