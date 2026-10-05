"""O que o piloto depende do leitor compartilhado, e o despacho sobre ele.

Estes testes nao reimplementam a suite de `tools/`: eles fixam as garantias de
que o CICLO depende. Se uma delas cair, o agente passa a investigar um recorte
diferente do que o documento promete, e a comparacao com o motor atual perde o
sentido -- por isso elas sao verificadas aqui tambem.
"""

from __future__ import annotations

import datetime as dt

import pytest
from conftest import FIM_JANELA, INICIO, SIM_NOW, fato, iso

from argus_agente.ferramentas import FerramentaIndisponivel, despachar, fact_ids_de
from argus_agente.leitor import CaseReader


def _caso(fatos, **extras):
    base = {
        "case_id": "c",
        "origin": "synthetic",
        "checkpoint_id": 1,
        "sim_now": iso(SIM_NOW),
        "input_lsn": 2000,
        "facts": fatos,
    }
    base.update(extras)
    return base


def test_fato_indisponivel_no_sim_now_nao_entra_no_recorte():
    visivel = fato(1, "prometheus", "http_5xx_rate", INICIO, 0.4)
    tardio = fato(2, "npaw_geo", "error_rate", INICIO, 9.9, atraso=100_800)
    leitor = CaseReader(_caso([visivel, tardio]))
    assert {f["metric"] for f in leitor.facts} == {"http_5xx_rate"}


def test_versao_posterior_ao_input_lsn_nao_entra_no_recorte():
    chave = "a" * 64
    antigo = fato(10, "prometheus", "http_5xx_rate", INICIO, 1.0, chave=chave)
    futuro = fato(5000, "prometheus", "http_5xx_rate", INICIO, 9.0, chave=chave)
    leitor = CaseReader(_caso([antigo, futuro], input_lsn=100))
    assert [f["value"] for f in leitor.facts] == [1.0]


def test_so_a_ultima_versao_de_cada_fato_aparece():
    chave = "b" * 64
    leitor = CaseReader(
        _caso(
            [
                fato(10, "prometheus", "http_5xx_rate", INICIO, 1.0, chave=chave),
                fato(20, "prometheus", "http_5xx_rate", INICIO, 8.1, chave=chave),
            ]
        )
    )
    assert [f["value"] for f in leitor.facts] == [8.1]


def test_fato_removido_desaparece_do_recorte():
    chave = "c" * 64
    leitor = CaseReader(
        _caso(
            [
                fato(10, "apollo", "latency_p95", INICIO, 92.0, atraso=900, chave=chave),
                fato(
                    20,
                    "apollo",
                    "latency_p95",
                    INICIO,
                    None,
                    atraso=900,
                    chave=chave,
                    apagado=True,
                ),
            ]
        )
    )
    assert leitor.facts == ()


def test_janela_depois_do_presente_simulado_e_recusada(ferramentas):
    with pytest.raises(ValueError, match="janela"):
        ferramentas.consultar_serie(
            source="prometheus",
            entity="playback",
            metric="http_5xx_rate",
            inicio=iso(INICIO),
            fim=iso(SIM_NOW + dt.timedelta(hours=1)),
        )


def test_contexto_enxerga_evento_iniciado_antes_da_janela(ferramentas):
    # O deploy comeca as 18:54 e termina as 18:58; pedir a partir das 18:56 so
    # o encontra se a ferramenta considerar `event_end`.
    resposta = ferramentas.consultar_contexto(
        entity="playback",
        kinds=["context"],
        inicio=iso(INICIO + dt.timedelta(minutes=116)),
        fim=iso(FIM_JANELA),
    )
    assert [item["metric"] for item in resposta["items"]] == ["deploy"]


def test_inventario_nao_devolve_fact_id_citavel(ferramentas):
    assert fact_ids_de(ferramentas.inventariar_fatos()) == []


def test_serie_devolve_identificadores_citaveis(ferramentas):
    envelope = ferramentas.consultar_serie(
        source="prometheus",
        entity="playback",
        metric="http_5xx_rate",
        inicio=iso(INICIO),
        fim=iso(FIM_JANELA),
    )
    assert len(fact_ids_de(envelope)) == envelope["returned"] == 13


def test_pagina_limitada_avisa_e_oferece_cursor(ferramentas):
    envelope = ferramentas.consultar_serie(
        source="prometheus",
        entity="playback",
        metric="http_5xx_rate",
        inicio=iso(INICIO),
        fim=iso(FIM_JANELA),
        limit=5,
    )
    assert envelope["returned"] == 5
    assert envelope["has_more"] and envelope["next_cursor"]
    assert "pagina_limitada" in envelope["limitations"]


def test_despacho_recusa_ferramenta_fora_do_contrato(ferramentas):
    with pytest.raises(FerramentaIndisponivel):
        despachar(ferramentas, "_page", {})
    with pytest.raises(FerramentaIndisponivel):
        despachar(ferramentas, "consultar_banco", {})
