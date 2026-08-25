"""Testes do ETL incremental: watermarks avancam, e so avancam com o dado."""

from __future__ import annotations

import time

import psycopg
import pytest
from argus_common import Metrics, ShutdownSignal

from argus_processing import etl
from argus_processing.__main__ import _drenar_silver_gold


def test_bronze_silver_sem_backlog_nao_mexe_no_watermark(db):
    antes = db.fetch_one(
        "SELECT lsn_processado FROM etl.watermark_bronze_silver WHERE id = 1"
    )

    resultado = etl.executar_bronze_silver(db, batch_size=100)

    assert resultado["status"] == "sem_pendencia"
    assert resultado["linhas"] == 0
    depois = db.fetch_one(
        "SELECT lsn_processado FROM etl.watermark_bronze_silver WHERE id = 1"
    )
    assert depois["lsn_processado"] == antes["lsn_processado"]


def test_bronze_silver_processa_e_avanca_watermark(db, inserir_change):
    with db.connection() as conn:
        inserir_change(
            conn,
            "signal_point",
            {
                "ts": 1783220400000,
                "source": "prometheus",
                "entity": "cdn-1",
                "metric": "p95_ms",
                "value": 368,
            },
        )
        lsn2 = inserir_change(
            conn,
            "signal_bucket",
            {
                "bts": 1783220400000,
                "source": "prometheus",
                "entity": "cdn-1",
                "metric": "p95_ms",
                "value": 368,
            },
        )
        conn.execute("SELECT bronze.merge_todas()")

    resultado = etl.executar_bronze_silver(db, batch_size=100)

    assert resultado["status"] == "sucesso"
    assert resultado["linhas"] == 2
    assert resultado["ate_lsn"] == lsn2

    watermark = db.fetch_one(
        "SELECT lsn_processado FROM etl.watermark_bronze_silver WHERE id = 1"
    )
    assert watermark["lsn_processado"] == lsn2

    ponto = db.fetch_one("SELECT source, value FROM silver.signal_point")
    assert ponto == {"source": "prometheus", "value": 368.0}

    execucao = db.fetch_one(
        "SELECT status, linhas_processadas FROM etl.execucoes"
        " WHERE worker = 'bronze_silver'"
    )
    assert execucao == {"status": "sucesso", "linhas_processadas": 2}

    # Rodar de novo sem novo backlog nao reprocessa nem duplica execucao.
    resultado_2 = etl.executar_bronze_silver(db, batch_size=100)
    assert resultado_2["status"] == "sem_pendencia"


def test_bronze_silver_respeita_batch_size_e_drena_em_varias_chamadas(db, inserir_change):
    with db.connection() as conn:
        for i in range(5):
            ponto = {
                "ts": 1783220400000 + i * 60_000,
                "source": "prometheus",
                "entity": f"cdn-{i}",
                "metric": "p95_ms",
                "value": 100 + i,
            }
            # pk explicito e distinto por linha: sem isso, as 5 mudancas
            # colapsam numa so no merge (ver docstring de inserir_change).
            inserir_change(
                conn,
                "signal_point",
                ponto,
                pk={
                    "ts": ponto["ts"],
                    "source": ponto["source"],
                    "entity": ponto["entity"],
                    "metric": ponto["metric"],
                },
            )
        conn.execute("SELECT bronze.merge_todas()")

    vistos = 0
    ciclos = 0
    while True:
        resultado = etl.executar_bronze_silver(db, batch_size=2)
        if resultado["status"] == "sem_pendencia":
            break
        assert resultado["status"] == "sucesso"
        vistos += resultado["linhas"]
        ciclos += 1
        assert ciclos <= 10, "nao deveria precisar de tantos ciclos para 5 linhas"

    assert vistos == 5
    assert ciclos == 3  # 2 + 2 + 1, com batch_size=2
    total = db.fetch_one("SELECT count(*) AS n FROM silver.signal_point")
    assert total["n"] == 5


def test_silver_gold_processa_janela_e_reabre_a_margem(db, inserir_change):
    with db.connection() as conn:
        inserir_change(
            conn,
            "signal_bucket",
            {
                "bts": 1783220400000,  # 2026-07-05 -- dentro da janela do watermark
                "source": "prometheus",
                "entity": "cdn-1",
                "metric": "p95_ms",
                "value": 368,
            },
        )
        conn.execute("SELECT bronze.merge_todas()")

    etl.executar_bronze_silver(db, batch_size=100)

    resultado = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)

    assert resultado["status"] == "sucesso"
    assert resultado["linhas"] >= 1

    watermark = db.fetch_one(
        "SELECT available_at_processado, margem_seguranca"
        "  FROM etl.watermark_silver_gold WHERE id = 1"
    )
    # O watermark nunca avanca ate o `ate_ts` puro -- sempre deixa a margem
    # de seguranca como faixa reaberta para o proximo ciclo.
    assert watermark["available_at_processado"] == (
        resultado["ate_ts"] - watermark["margem_seguranca"]
    )

    bucket = db.fetch_one("SELECT source, value, tem_jogo FROM gold.feature_bucket")
    assert bucket == {"source": "prometheus", "value": 368.0, "tem_jogo": False}


def test_silver_gold_recusa_janela_menor_ou_igual_a_margem(db):
    """Regressao: com janela <= margem, o watermark REGRIDE a cada chamada em
    vez de so travar (a margem e subtraida nas duas pontas do ciclo). A funcao
    tem que falhar alto em vez de girar para tras silenciosamente.
    """
    with pytest.raises(psycopg.Error):
        db.fetch_one(
            "SELECT * FROM etl.executar_silver_gold(%s)", (7200,)
        )  # == margem default


def test_drenar_silver_gold_nao_gira_para_sempre_com_relogio_correndo(db):
    """Regressao: sim.now() anda em tempo real (speed=1.0), entao reavaliar o
    alvo a cada iteracao do dreno nunca converge (`ate_ts < sim.now()` fica
    verdadeiro para sempre, por uma fracao de segundo cada vez). O dreno
    precisa congelar o alvo no inicio -- ver docstring de `_drenar_silver_gold`.
    """
    with db.connection() as conn:
        conn.execute(
            "UPDATE etl.watermark_silver_gold"
            "   SET available_at_processado = sim.now() - interval '1 minute'"
            " WHERE id = 1"
        )

    inicio = time.monotonic()
    _drenar_silver_gold(
        # > margem_seguranca (2h por default -- ver 015_etl_incremental.sql),
        # senao etl.executar_silver_gold recusa rodar (guarda de configuracao).
        db,
        Metrics("Argus/Test", "test"),
        janela_max_segundos=14400,
        shutdown=ShutdownSignal(),
    )
    duracao = time.monotonic() - inicio

    assert duracao < 5.0, f"dreno deveria convergir rapido, levou {duracao:.1f}s"


def test_silver_gold_nunca_ultrapassa_sim_now(db):
    resultado = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)

    # sim.now() medido DEPOIS da chamada: o relogio (speed=1.0) so anda para a
    # frente, entao esse limite superior e valido mesmo com o tempo de parede
    # que passou entre o calculo de ate_ts dentro da funcao e esta leitura.
    assert resultado["status"] == "sucesso"
    assert resultado["ate_ts"] <= db.sim_now()
