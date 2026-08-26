"""Commit atomico protegido pelo fencing token global."""

from __future__ import annotations

import pytest

from argus_processing.orchestration import (
    FencingRejected,
    commit_protegido,
    iniciar_trabalho,
    reivindicar_trabalho,
)

MANIFEST_HASH = "manifest-stage-1"


def _expirar_claim(db, run_id: int) -> None:
    """Simula lease vencido mantendo heartbeat anterior ao vencimento."""
    with db.connection() as conn:
        conn.execute(
            """
            UPDATE detect.run
               SET heartbeat_at = clock_timestamp() - interval '2 minutes',
                   lease_expires_at = clock_timestamp() - interval '1 minute'
             WHERE run_id = %s
            """,
            (run_id,),
        )
        conn.execute(
            """
            UPDATE detect.work_claim
               SET heartbeat_at = clock_timestamp() - interval '2 minutes',
                   lease_expires_at = clock_timestamp() - interval '1 minute'
             WHERE run_id = %s
            """,
            (run_id,),
        )


def _inserir_anomalia(conn, run_id: int, entity: str) -> None:
    """Insere um resultado filho dentro da transacao protegida."""
    conn.execute(
        """
        INSERT INTO detect.anomaly (
          run_id, bucket_ts, source, entity, metric, z, score, n_sources
        ) VALUES (
          %s, timestamptz '2026-07-12 10:00:00+00',
          'test', %s, 'error_rate', 4.0, 80.0, 1
        )
        """,
        (run_id, entity),
    )


def test_worker_zumbi_nao_consegue_fazer_commit(db, checkpoint):
    """O token anterior e rejeitado depois de um takeover."""
    zumbi = reivindicar_trabalho(
        db,
        worker_id="worker-zumbi",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=30,
    )
    assert zumbi is not None
    assert iniciar_trabalho(db, zumbi)
    _expirar_claim(db, zumbi.run_id)

    atual = reivindicar_trabalho(
        db,
        worker_id="worker-atual",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=60,
    )
    assert atual is not None
    assert iniciar_trabalho(db, atual)

    recebeu_conexao = False
    with (
        pytest.raises(FencingRejected, match="perdeu lease ou fencing"),
        commit_protegido(db, zumbi),
    ):
        recebeu_conexao = True
    assert not recebeu_conexao

    with commit_protegido(db, atual) as conn:
        _inserir_anomalia(conn, atual.run_id, "worker-atual")

    statuses = db.fetch_all("SELECT run_id, status FROM detect.run ORDER BY run_id")
    assert statuses == [
        {"run_id": zumbi.run_id, "status": "abandoned"},
        {"run_id": atual.run_id, "status": "completed"},
    ]
    assert db.fetch_one("SELECT count(*) AS n FROM detect.anomaly")["n"] == 1


def test_falha_na_persistencia_reverte_resultado_e_estado(db, checkpoint):
    """Resultado parcial e estado committing desaparecem no mesmo rollback."""
    claim = reivindicar_trabalho(
        db,
        worker_id="worker-a",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=60,
    )
    assert claim is not None
    assert iniciar_trabalho(db, claim)

    with (
        pytest.raises(RuntimeError, match="falha simulada"),
        commit_protegido(db, claim) as conn,
    ):
        _inserir_anomalia(conn, claim.run_id, "resultado-parcial")
        raise RuntimeError("falha simulada")

    run = db.fetch_one(
        "SELECT status, finished_at FROM detect.run WHERE run_id = %s",
        (claim.run_id,),
    )
    assert run == {"status": "running", "finished_at": None}
    assert db.fetch_one("SELECT count(*) AS n FROM detect.anomaly")["n"] == 0

    with commit_protegido(db, claim) as conn:
        _inserir_anomalia(conn, claim.run_id, "resultado-final")

    assert (
        db.fetch_one("SELECT status FROM detect.run WHERE run_id = %s", (claim.run_id,))[
            "status"
        ]
        == "completed"
    )


def test_run_concluido_nao_e_reivindicado_novamente(db, checkpoint):
    """Checkpoint + manifesto concluido e uma unidade logica idempotente."""
    claim = reivindicar_trabalho(
        db,
        worker_id="worker-a",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=60,
    )
    assert claim is not None
    assert iniciar_trabalho(db, claim)
    with commit_protegido(db, claim):
        pass

    repetido = reivindicar_trabalho(
        db,
        worker_id="worker-b",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=60,
    )
    assert repetido is None
