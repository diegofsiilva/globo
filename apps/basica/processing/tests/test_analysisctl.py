"""Portao de promocao do manifesto (`analysisctl evaluate-and-promote`).

O comando roda uma vez por rollout e e o unico caminho que publica um
manifesto. Ele precisa de teste proprio porque a consulta tem um `LIKE` com
`%`, e um `%` solto num parametro de psycopg vira placeholder: o comando
inteiro morria antes de avaliar qualquer criterio.
"""

from __future__ import annotations

import argparse

from argus_processing.analysis_repository import register_manifest
from argus_processing.analysisctl import FAMILIES, evaluate
from argus_processing.catalog import Catalog


def _args(**overrides) -> argparse.Namespace:
    base = {
        "precision_at_5": 0.70,
        "api_p95_ms": 900.0,
        "api_max_ms": 2500.0,
        "checkpoint_sla_ok": True,
        "suite_ok": True,
    }
    return argparse.Namespace(**{**base, **overrides})


def _registrar(db) -> Catalog:
    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")
    return catalog


def test_portao_avalia_sem_quebrar_e_bloqueia_manifesto_sem_prova(db):
    catalog = _registrar(db)
    metrics = evaluate(db, catalog, _args())

    # Executou a consulta ate o fim (regressao do placeholder do LIKE).
    assert metrics["digest_divergence"] == 0
    assert metrics["completed_runs"] == 0
    # E recusou: sem run concluido e sem as 11 familias, nao ha o que publicar.
    assert "nenhum run concluido" in metrics["failures"]
    assert any("familias sem resultado" in item for item in metrics["failures"])


def test_portao_enxerga_retry_com_digest_divergente(db, checkpoint):
    """O `LIKE 'input_digest_mismatch:%'` precisa casar de verdade."""
    catalog = _registrar(db)
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO detect.run (
              detector, params, checkpoint_id, manifest_hash, sim_now, status,
              claimed_by, lease_expires_at, heartbeat_at, fencing_token,
              attempt, input_lsn, stream_key, started_at, finished_at,
              error_message
            ) VALUES (
              'argus-rules', '{}'::jsonb, %s, %s, sim.now(), 'failed',
              'w', clock_timestamp(), clock_timestamp(),
              nextval('detect.fencing_token_seq'), 2, 1, 'live',
              clock_timestamp(), clock_timestamp(),
              'input_digest_mismatch:aaa!=bbb'
            )
            """,
            (checkpoint["checkpoint_id"], catalog.manifest_hash),
        )

    metrics = evaluate(db, catalog, _args())
    assert metrics["digest_divergence"] == 1
    assert metrics["failed_runs"] == 1
    assert "ha retry com digest divergente" in metrics["failures"]
    assert "ha runs com falha" in metrics["failures"]


def test_portao_reprova_cada_criterio_operacional_do_plano(db):
    catalog = _registrar(db)

    reprovado = evaluate(db, catalog, _args(precision_at_5=0.50))
    assert "precision@5 abaixo de 0.60" in reprovado["failures"]

    lento = evaluate(db, catalog, _args(api_p95_ms=3500.0))
    assert "API fora do SLO" in lento["failures"]

    estourado = evaluate(db, catalog, _args(api_max_ms=5200.0))
    assert "API fora do SLO" in estourado["failures"]

    atrasado = evaluate(db, catalog, _args(checkpoint_sla_ok=False))
    assert "processamento nao acompanha checkpoints" in atrasado["failures"]

    sem_suite = evaluate(db, catalog, _args(suite_ok=False))
    assert "suite e cenarios das 11 familias nao confirmados" in sem_suite["failures"]


def test_portao_cobre_exatamente_as_onze_familias():
    assert len(FAMILIES) == 11
