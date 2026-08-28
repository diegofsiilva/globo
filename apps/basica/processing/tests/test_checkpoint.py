"""Checkpoint publicado pelo ciclo silver->gold."""

from __future__ import annotations

import psycopg
import pytest

from argus_processing import etl


def test_silver_gold_publica_checkpoint_ligado_a_execucao(db):
    """Sucesso do ETL, watermark e checkpoint descrevem o mesmo commit."""
    resultado = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)

    assert resultado["status"] == "sucesso"

    checkpoint = db.fetch_one(
        """
        SELECT checkpoint_id, etl_execution_id, ready_through,
               source_lsn, row_counts
          FROM etl.gold_checkpoint
        """
    )
    assert checkpoint is not None
    assert checkpoint["ready_through"] == resultado["ate_ts"]
    assert checkpoint["source_lsn"] == 0
    assert checkpoint["row_counts"]["total"] == resultado["linhas"]

    execucao = db.fetch_one(
        """
        SELECT execucao_id, status, linhas_processadas
          FROM etl.execucoes
         WHERE worker = 'silver_gold'
        """
    )
    assert execucao == {
        "execucao_id": checkpoint["etl_execution_id"],
        "status": "sucesso",
        "linhas_processadas": resultado["linhas"],
    }

    watermark = db.fetch_one(
        """
        SELECT execucao_id
          FROM etl.watermark_silver_gold
         WHERE id = 1
        """
    )
    assert watermark["execucao_id"] == checkpoint["etl_execution_id"]


def test_cada_ciclo_bem_sucedido_acrescenta_checkpoint(db):
    """Checkpoint forma historico; o ciclo seguinte nao substitui o anterior."""
    primeiro = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)
    segundo = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)

    assert primeiro["status"] == "sucesso"
    assert segundo["status"] == "sucesso"

    checkpoints = db.fetch_all(
        """
        SELECT checkpoint_id, ready_through
          FROM etl.gold_checkpoint
         ORDER BY checkpoint_id
        """
    )
    assert len(checkpoints) == 2
    assert checkpoints[0]["checkpoint_id"] < checkpoints[1]["checkpoint_id"]
    assert checkpoints[0]["ready_through"] <= checkpoints[1]["ready_through"]


def test_configuracao_invalida_nao_publica_checkpoint(db):
    """Uma chamada rejeitada antes do build nao anuncia uma Gold inexistente."""
    with pytest.raises(psycopg.Error):
        etl.executar_silver_gold(db, janela_max_segundos=7200)

    total = db.fetch_one("SELECT count(*) AS n FROM etl.gold_checkpoint")
    assert total["n"] == 0


def test_checkpoint_publicado_e_append_only(db):
    """Uma versao publicada nao pode ser corrigida ou removida em silencio."""
    resultado = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)
    assert resultado["status"] == "sucesso"

    checkpoint = db.fetch_one("SELECT checkpoint_id FROM etl.gold_checkpoint")

    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        db.fetch_one(
            """
            UPDATE etl.gold_checkpoint
               SET ready_through = ready_through + interval '1 minute'
             WHERE checkpoint_id = %s
         RETURNING checkpoint_id
            """,
            (checkpoint["checkpoint_id"],),
        )

    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        db.fetch_one(
            """
            DELETE FROM etl.gold_checkpoint
             WHERE checkpoint_id = %s
         RETURNING checkpoint_id
            """,
            (checkpoint["checkpoint_id"],),
        )

    total = db.fetch_one("SELECT count(*) AS n FROM etl.gold_checkpoint")
    assert total["n"] == 1
