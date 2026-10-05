"""A checagem numerica precisa pegar texto que contradiz a serie, e so isso."""

from __future__ import annotations

import datetime as dt
import hashlib

from conftest import fato, iso

from argus_agente.checagem import checar_evidencias, direcao_do_texto, magnitude_do_texto
from argus_agente.leitor import CaseReader

INICIO = dt.datetime(2026, 8, 21, 2, 0, tzinfo=dt.UTC)


def _leitor(
    valores: list[float], *, metric: str = "error_5xx_rate_pct", source: str = "rpaas"
):
    """Serie de 15 em 15 minutos a partir de INICIO, sem nenhum outro fato."""
    fatos = [
        fato(
            100 + i,
            source,
            metric,
            INICIO + dt.timedelta(minutes=15 * i),
            valor,
            role="subject",
            chave=hashlib.sha256(f"{metric}-{i}".encode()).hexdigest(),
        )
        for i, valor in enumerate(valores)
    ]
    for f in fatos:
        f["entity"] = "playback"
    caso = {
        "case_id": "checagem",
        "origin": "synthetic",
        "checkpoint_id": 1,
        "sim_now": iso(INICIO + dt.timedelta(hours=8)),
        "input_lsn": 1000,
        "facts": fatos,
    }
    return CaseReader(caso)


def _hipotese(texto: str, ids: list[str], efeito: str, lado: str = "evidence_for"):
    hipotese = {"effect_start": efeito, "evidence_for": [], "evidence_against": []}
    hipotese[lado] = [{"fact_ids": ids, "observation": texto, "reading": "x"}]
    return hipotese


def _ids(leitor):
    return [f"{f['fact_key']}:{f['version_lsn']}" for f in leitor.facts]


def _ids_a_partir_de(leitor, minutos: int):
    """Ids dos pontos cuja hora de evento vem a partir de `minutos` depois do inicio."""
    corte = INICIO + dt.timedelta(minutes=minutos)
    ordenados = sorted(leitor.facts, key=lambda f: f["event_start"])
    return [
        f"{f['fact_key']}:{f['version_lsn']}"
        for f in ordenados
        if dt.datetime.fromisoformat(f["event_start"].replace("Z", "+00:00")) >= corte
    ]


def test_direcao_vem_do_texto_sem_acento_e_ambiguidade_vira_none():
    assert direcao_do_texto("a taxa sobe a partir das 19h") == "alta"
    assert direcao_do_texto("o volume cai") == "queda"
    assert direcao_do_texto("o valor permanece estavel") == "estavel"
    assert direcao_do_texto("sobe e depois cai") is None
    assert direcao_do_texto("os valores foram anotados") is None


def test_magnitude_reconhece_adjetivos_de_forca():
    assert magnitude_do_texto("aumento significativo do erro")
    assert not magnitude_do_texto("o erro subiu um pouco")


def test_texto_que_contradiz_a_serie_vira_problema():
    # Serie sobe de 0,2 para 0,4 no efeito; o texto diz que cai.
    valores = [0.2] * 8 + [0.4] * 8
    leitor = _leitor(valores)
    efeito = iso(INICIO + dt.timedelta(minutes=120))
    ids = _ids_a_partir_de(leitor, 120)
    problemas, checagens = checar_evidencias(
        _hipotese("o erro cai a partir do efeito", ids, efeito), leitor
    )
    assert problemas and "afirma queda" in problemas[0]
    assert checagens[0]["status"] == "contradito"


def test_texto_coerente_com_a_serie_passa():
    valores = [0.2] * 8 + [0.4] * 8
    leitor = _leitor(valores)
    efeito = iso(INICIO + dt.timedelta(minutes=120))
    problemas, checagens = checar_evidencias(
        _hipotese(
            "o erro sobe a partir do efeito", _ids_a_partir_de(leitor, 120), efeito
        ),
        leitor,
    )
    assert problemas == []
    assert checagens[0]["status"] == "confirmado"


def test_adjetivo_forte_para_variacao_pequena_vira_exagero():
    # +25%: a serie sobe, mas nao "significativamente".
    valores = [0.20] * 8 + [0.25] * 8
    leitor = _leitor(valores)
    efeito = iso(INICIO + dt.timedelta(minutes=120))
    problemas, checagens = checar_evidencias(
        _hipotese("aumento significativo do erro", _ids_a_partir_de(leitor, 120), efeito),
        leitor,
    )
    assert problemas and "magnitude" in problemas[0]
    assert checagens[0]["status"] == "exagero"


def test_evidencia_com_fatos_de_duas_series_fica_indeterminada():
    valores = [0.2] * 8 + [0.4] * 8
    leitor = _leitor(valores)
    misturada = [_ids_a_partir_de(leitor, 120)[0], "fato-de-outra-serie:9"]
    problemas, checagens = checar_evidencias(
        _hipotese("o erro cai", misturada, iso(INICIO + dt.timedelta(minutes=120))),
        leitor,
    )
    assert problemas == []
    assert checagens[0]["status"] == "indeterminado"


def test_sem_pontos_depois_do_efeito_nao_contradiz_ninguem():
    valores = [0.2] * 8
    leitor = _leitor(valores)
    problemas, checagens = checar_evidencias(
        _hipotese("o erro cai", _ids(leitor), iso(INICIO + dt.timedelta(hours=5))), leitor
    )
    assert problemas == []
    assert checagens[0]["status"] == "indeterminado"
