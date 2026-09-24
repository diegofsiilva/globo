"""Contratos fim a fim da captura versionada e do commit de analise."""

from __future__ import annotations

import datetime as dt

from argus_common import Metrics

from argus_processing import etl
from argus_processing.analysis_repository import (
    claim_and_capture,
    promote_manifest,
    register_manifest,
)
from argus_processing.catalog import Catalog
from argus_processing.orchestration import falhar_trabalho, iniciar_trabalho
from argus_processing.pipeline import analyze_once


def _epoch_ms(value: dt.datetime) -> int:
    return int(value.timestamp() * 1000)


def test_change_log_preserva_todas_as_versoes_e_tombstone(db, inserir_change):
    instant = dt.datetime(2026, 7, 12, 10, tzinfo=dt.UTC)
    pk = {
        "bts": _epoch_ms(instant),
        "source": "prometheus",
        "entity": "playback",
        "metric": "latency_ms_avg",
    }
    with db.connection() as conn:
        first = inserir_change(conn, "signal_bucket", {**pk, "value": 100}, pk=pk)
        second = inserir_change(
            conn, "signal_bucket", {**pk, "value": 250}, pk=pk, op="u"
        )
        deleted = inserir_change(conn, "signal_bucket", pk, pk=pk, op="d")
        conn.execute("SELECT bronze.merge_todas()")

    outcome = etl.executar_bronze_silver(db, batch_size=100)
    assert outcome["status"] == "sucesso"
    assert outcome["ate_lsn"] == deleted

    versions = db.fetch_all(
        """
        SELECT version_lsn, value, is_deleted
          FROM silver.analysis_fact_version
         ORDER BY version_lsn
        """
    )
    assert versions == [
        {"version_lsn": first, "value": 100.0, "is_deleted": False},
        {"version_lsn": second, "value": 250.0, "is_deleted": False},
        {"version_lsn": deleted, "value": None, "is_deleted": True},
    ]


def test_pipeline_captura_checkpoint_commita_e_so_publica_depois_do_gate(
    db, inserir_change
):
    instant = dt.datetime(2026, 7, 12, 10, tzinfo=dt.UTC)
    row = {
        "bts": _epoch_ms(instant),
        "source": "prometheus",
        "entity": "playback",
        "metric": "latency_ms_avg",
        "value": 100,
    }
    with db.connection() as conn:
        lsn = inserir_change(conn, "signal_bucket", row)
        conn.execute("SELECT bronze.merge_todas()")
    assert etl.executar_bronze_silver(db, batch_size=100)["status"] == "sucesso"
    assert (
        etl.executar_silver_gold(db, janela_max_segundos=999_999_999)["status"]
        == "sucesso"
    )

    catalog = Catalog("test")
    worked = analyze_once(
        db,
        Metrics("Argus/Test", "analysis"),
        catalog,
        worker_id="test-worker",
        code_version="test",
    )
    assert worked

    run = db.fetch_one(
        """
        SELECT status, sim_now, input_lsn, input_digest, input_rows
          FROM detect.run
         WHERE manifest_hash = %s
        """,
        (catalog.manifest_hash,),
    )
    assert run["status"] == "completed"
    assert run["input_lsn"] == lsn
    assert len(run["input_digest"]) == 64
    assert run["input_rows"] == 1
    assert db.fetch_one("SELECT count(*) AS n FROM gold.v_hypothesis_run")["n"] == 0

    captured = db.fetch_one(
        """
        SELECT f.version_lsn, f.available_at, r.sim_now
          FROM detect.run_input_fact i
          JOIN silver.analysis_fact_version f
            ON f.fact_key = i.fact_key AND f.version_lsn = i.version_lsn
          JOIN detect.run r ON r.run_id = i.run_id
        """
    )
    assert captured["version_lsn"] == lsn
    assert captured["available_at"] <= captured["sim_now"]

    promote_manifest(db, catalog.manifest_hash, {"test": True})
    assert db.fetch_one("SELECT count(*) AS n FROM gold.v_hypothesis_run")["n"] == 1


def test_retry_reconstroi_digest_mesmo_se_silver_avancar(db, inserir_change):
    instant = dt.datetime(2026, 7, 12, 10, tzinfo=dt.UTC)
    first_row = {
        "bts": _epoch_ms(instant),
        "source": "prometheus",
        "entity": "playback",
        "metric": "latency_ms_avg",
        "value": 100,
    }
    with db.connection() as conn:
        first_lsn = inserir_change(conn, "signal_bucket", first_row)
        conn.execute("SELECT bronze.merge_todas()")
    etl.executar_bronze_silver(db, batch_size=100)
    etl.executar_silver_gold(db, janela_max_segundos=999_999_999)

    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")
    first = claim_and_capture(
        db, worker_id="worker-first", manifest_hash=catalog.manifest_hash
    )
    assert first is not None
    digest = db.fetch_one(
        "SELECT input_digest FROM detect.run WHERE run_id = %s",
        (first.claim.run_id,),
    )["input_digest"]
    assert iniciar_trabalho(db, first.claim)
    assert falhar_trabalho(db, first.claim, "falha simulada")

    second_row = {**first_row, "bts": _epoch_ms(instant + dt.timedelta(minutes=15))}
    with db.connection() as conn:
        second_lsn = inserir_change(conn, "signal_bucket", second_row)
        conn.execute("SELECT bronze.merge_todas()")
    etl.executar_bronze_silver(db, batch_size=100)
    assert second_lsn > first_lsn

    retry = claim_and_capture(
        db, worker_id="worker-retry", manifest_hash=catalog.manifest_hash
    )
    assert retry is not None
    assert retry.claim.retry_of == first.claim.run_id
    assert retry.claim.input_lsn == first_lsn
    assert [fact.version_lsn for fact in retry.facts] == [first_lsn]
    assert (
        db.fetch_one(
            "SELECT input_digest FROM detect.run WHERE run_id = %s",
            (retry.claim.run_id,),
        )["input_digest"]
        == digest
    )
