"""O recorte precisa esconder o futuro e explicar o vazio."""

from __future__ import annotations

import datetime as dt

from conftest import INICIO, ponto

from argus_agente.ferramentas import FerramentasDeFixture


def test_fato_indisponivel_nao_entra_no_recorte(recorte):
    tardio = ponto(0, 9.9, atraso=100_800, metric="error_rate", source="npaw_geo")
    ferramentas = FerramentasDeFixture(recorte, [ponto(0, 0.4), tardio])
    assert [linha.fact_id for linha in ferramentas.fatos] == [
        "prometheus:http_5xx_rate:0"
    ]


def test_fonte_atrasada_vira_lacuna_de_cobertura_sem_valor(recorte):
    tardio = ponto(0, 9.9, atraso=100_800, metric="error_rate", source="npaw_geo")
    ferramentas = FerramentasDeFixture(recorte, [tardio])
    (lacuna,) = ferramentas.lacunas_de_cobertura
    assert lacuna["source"] == "npaw_geo"
    assert "9.9" not in str(lacuna)


def test_serie_vazia_distingue_fonte_ausente_de_periodo_sem_ponto(ferramentas):
    fora = ferramentas.serie(
        source="prometheus",
        entity="playback",
        metric="http_5xx_rate",
        inicio=INICIO - dt.timedelta(hours=5),
        fim=INICIO - dt.timedelta(hours=4),
    )
    assert "nao tem ponto no periodo pedido" in fora.vazia_porque

    inexistente = ferramentas.serie(
        source="apollo",
        entity="playback",
        metric="latency_p95",
        inicio=INICIO,
        fim=INICIO + dt.timedelta(hours=3),
    )
    assert inexistente.vazia_porque == "a fonte apollo nao esta no recorte"


def test_agregacao_preserva_os_fatos_de_origem(ferramentas):
    resposta = ferramentas.serie(
        source="prometheus",
        entity="playback",
        metric="http_5xx_rate",
        inicio=INICIO,
        fim=INICIO + dt.timedelta(hours=3),
        agregacao="media_por_bucket",
    )
    assert all(len(linha.fact_ids) >= 1 for linha in resposta.linhas)
    assert sum(len(linha.fact_ids) for linha in resposta.linhas) == 13


def test_teto_de_linhas_marca_a_resposta_como_truncada(ferramentas):
    resposta = ferramentas.serie(
        source="prometheus",
        entity="playback",
        metric="http_5xx_rate",
        inicio=INICIO,
        fim=INICIO + dt.timedelta(hours=3),
        limite=3,
    )
    assert len(resposta.linhas) == 3
    assert resposta.truncada


def test_contexto_lista_os_tipos_presentes_quando_nao_acha_o_pedido(ferramentas):
    resposta = ferramentas.contexto(
        tipos=("live_event",), inicio=INICIO, fim=INICIO + dt.timedelta(hours=3)
    )
    assert resposta.linhas == ()
    assert "deploy" in resposta.vazia_porque


def test_inventario_nao_mistura_contexto_com_serie(ferramentas):
    metricas = {item.metric for item in ferramentas.inventario()}
    assert metricas == {"http_5xx_rate"}


def test_consulta_a_fonte_atrasada_explica_o_atraso_em_vez_de_negar_a_serie(recorte):
    tardio = ponto(0, 9.9, atraso=100_800, metric="error_rate", source="npaw_geo")
    ferramentas = FerramentasDeFixture(recorte, [ponto(0, 0.4), tardio])
    resposta = ferramentas.serie(
        source="npaw_geo",
        entity="playback",
        metric="error_rate",
        inicio=INICIO,
        fim=INICIO + dt.timedelta(hours=3),
    )
    assert "so fica disponivel em" in resposta.vazia_porque
    assert "9.9" not in resposta.vazia_porque
