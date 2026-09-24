"""Hipóteses geradas ficam visíveis sem publicação manual."""

from __future__ import annotations

from argus_processing.analysis_repository import register_manifest
from argus_processing.catalog import Catalog


def test_hipoteses_geradas_visiveis_sem_publicacao(db, checkpoint):
    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")

    with db.connection() as conn:
        run_id = conn.execute(
            """
            INSERT INTO detect.run (
              detector, params, checkpoint_id, manifest_hash, sim_now, status,
              claimed_by, lease_expires_at, heartbeat_at, fencing_token,
              attempt, input_lsn, stream_key, started_at, finished_at
            ) VALUES (
              'argus-rules', '{}'::jsonb, %s, %s, sim.now(), 'completed',
              'teste', clock_timestamp(), clock_timestamp(),
              nextval('detect.fencing_token_seq'), 1, %s, 'live',
              clock_timestamp(), clock_timestamp()
            ) RETURNING run_id
            """,
            (
                checkpoint["checkpoint_id"],
                catalog.manifest_hash,
                checkpoint["source_lsn"],
            ),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO gold.hypothesis_run_stats (run_id) VALUES (%s)", (run_id,)
        )
        hypothesis_ids = []
        for index in (1, 2):
            hypothesis_ids.append(
                conn.execute(
                    """
                    INSERT INTO gold.hypothesis (
                      run_id, family, kind, title, summary, scope,
                      effect_start, effect_end, score, coverage, confidence,
                      evaluation_status, dedup_key, lineage_key, revision
                    ) VALUES (
                      %s, 'backend_internal', 'operational', %s, 'Teste',
                      '{}'::jsonb, sim.now() - interval '15 minutes',
                      sim.now() - interval '15 minutes', 90, 0.8, 'high',
                      'generated', %s, %s, 1
                    ) RETURNING hypothesis_id
                    """,
                    (run_id, f"Hipótese {index}", str(index) * 64, str(index) * 64),
                ).fetchone()[0]
            )

    assert db.fetch_one("SELECT count(*) AS n FROM gold.v_hypothesis")["n"] == 2
    with db.connection() as conn:
        revised_id = conn.execute(
            """
            INSERT INTO gold.hypothesis (
              run_id, family, kind, title, summary, scope,
              effect_start, effect_end, score, coverage, confidence,
              evaluation_status, dedup_key, lineage_key, revision,
              supersedes_hypothesis_id
            ) VALUES (
              %s, 'backend_internal', 'operational', 'Revisão', 'Teste',
              '{}'::jsonb, sim.now() - interval '15 minutes',
              sim.now() - interval '15 minutes', 91, 0.8, 'high',
              'generated', %s, %s, 2, %s
            ) RETURNING hypothesis_id
            """,
            (run_id, "3" * 64, "1" * 64, hypothesis_ids[0]),
        ).fetchone()[0]
    expected_ids = {*hypothesis_ids, revised_id}
    visible = db.fetch_all("SELECT hypothesis_id FROM gold.v_hypothesis")
    assert {row["hypothesis_id"] for row in visible} == expected_ids
    assert db.fetch_one(
        "SELECT hypothesis_id FROM gold.v_hypothesis_detail WHERE hypothesis_id = %s",
        (hypothesis_ids[0],),
    ) == {"hypothesis_id": hypothesis_ids[0]}
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.manifest_publication_event
              (manifest_hash, action, gate_metrics)
            VALUES (%s, 'preview', %s::jsonb)
            """,
            (catalog.manifest_hash, f'{{"hypothesis_id": {hypothesis_ids[0]}}}'),
        )
    visible = db.fetch_all("SELECT hypothesis_id FROM gold.v_hypothesis")
    assert {row["hypothesis_id"] for row in visible} == expected_ids
    assert db.fetch_one("SELECT count(*) AS n FROM gold.v_hypothesis_run")["n"] == 1

    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.manifest_publication_event
              (manifest_hash, action, gate_metrics)
            VALUES (%s, 'withdrawn', '{}'::jsonb)
            """,
            (catalog.manifest_hash,),
        )
    assert db.fetch_one("SELECT count(*) AS n FROM gold.v_hypothesis")["n"] == 3

    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.manifest_publication_event
              (manifest_hash, action, gate_metrics)
            VALUES (%s, 'published', '{}'::jsonb)
            """,
            (catalog.manifest_hash,),
        )
    assert db.fetch_one("SELECT count(*) AS n FROM gold.v_hypothesis")["n"] == 3
