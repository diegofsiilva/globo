"""Claim, lease e takeover da coordenacao de analise."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from argus_processing.orchestration import (
    falhar_trabalho,
    iniciar_trabalho,
    reivindicar_trabalho,
    renovar_lease,
)

MANIFEST_HASH = "a" * 64


def _expirar_claim(db, run_id: int) -> None:
    """Move heartbeat e lease para o passado sem violar a ordem entre eles."""
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


def test_dois_workers_disputam_o_mesmo_checkpoint(db, checkpoint):
    """Somente uma replica recebe a posse logica do checkpoint + manifesto."""
    barreira = Barrier(2)

    def reivindicar(worker_id: str):
        barreira.wait()
        return reivindicar_trabalho(
            db,
            worker_id=worker_id,
            manifest_hash=MANIFEST_HASH,
            lease_seconds=60,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(reivindicar, ("worker-a", "worker-b")))

    claims = [claim for claim in resultados if claim is not None]
    assert len(claims) == 1
    assert claims[0].checkpoint_id == checkpoint["checkpoint_id"]

    runs = db.fetch_all(
        """
        SELECT run_id, status, attempt
          FROM detect.run
         WHERE checkpoint_id = %s AND manifest_hash = %s
        """,
        (checkpoint["checkpoint_id"], MANIFEST_HASH),
    )
    assert len(runs) == 1
    assert runs[0]["status"] == "claimed"
    assert runs[0]["attempt"] == 1


def test_heartbeat_renova_lease_sem_trocar_fencing(db, checkpoint):
    """O proprietario ativo estende o lease mantendo o mesmo token."""
    claim = reivindicar_trabalho(
        db,
        worker_id="worker-a",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=30,
    )
    assert claim is not None
    assert iniciar_trabalho(db, claim)

    antes = db.fetch_one(
        """
        SELECT heartbeat_at, lease_expires_at, fencing_token
          FROM detect.run WHERE run_id = %s
        """,
        (claim.run_id,),
    )
    assert renovar_lease(db, claim, lease_seconds=120)
    depois = db.fetch_one(
        """
        SELECT heartbeat_at, lease_expires_at, fencing_token
          FROM detect.run WHERE run_id = %s
        """,
        (claim.run_id,),
    )

    assert depois["heartbeat_at"] >= antes["heartbeat_at"]
    assert depois["lease_expires_at"] > antes["lease_expires_at"]
    assert depois["fencing_token"] == antes["fencing_token"]


def test_lease_expirado_permite_takeover(db, checkpoint):
    """Takeover abandona a tentativa anterior e cria token global novo."""
    antigo = reivindicar_trabalho(
        db,
        worker_id="worker-antigo",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=30,
    )
    assert antigo is not None
    assert iniciar_trabalho(db, antigo)
    _expirar_claim(db, antigo.run_id)

    novo = reivindicar_trabalho(
        db,
        worker_id="worker-novo",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=60,
    )
    assert novo is not None
    assert novo.run_id != antigo.run_id
    assert novo.retry_of == antigo.run_id
    assert novo.attempt == antigo.attempt + 1
    assert novo.fencing_token > antigo.fencing_token
    assert not renovar_lease(db, antigo, lease_seconds=60)

    runs = db.fetch_all(
        """
        SELECT run_id, status, retry_of, attempt
          FROM detect.run
         WHERE checkpoint_id = %s AND manifest_hash = %s
         ORDER BY attempt
        """,
        (checkpoint["checkpoint_id"], MANIFEST_HASH),
    )
    assert runs == [
        {
            "run_id": antigo.run_id,
            "status": "abandoned",
            "retry_of": None,
            "attempt": 1,
        },
        {
            "run_id": novo.run_id,
            "status": "claimed",
            "retry_of": antigo.run_id,
            "attempt": 2,
        },
    ]


def test_falha_conhecida_pode_ser_retentada(db, checkpoint):
    """Falha encerra a posse e a proxima tentativa preserva sua linhagem."""
    falho = reivindicar_trabalho(
        db,
        worker_id="worker-falho",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=60,
    )
    assert falho is not None
    assert iniciar_trabalho(db, falho)
    assert falhar_trabalho(db, falho, "entrada invalida")

    retry = reivindicar_trabalho(
        db,
        worker_id="worker-retry",
        manifest_hash=MANIFEST_HASH,
        lease_seconds=60,
    )
    assert retry is not None
    assert retry.retry_of == falho.run_id
    assert retry.attempt == 2
    assert retry.fencing_token > falho.fencing_token

    anterior = db.fetch_one(
        "SELECT status, error_message FROM detect.run WHERE run_id = %s",
        (falho.run_id,),
    )
    assert anterior == {"status": "failed", "error_message": "entrada invalida"}
