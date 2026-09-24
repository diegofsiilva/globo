"""API publica de runs, hipoteses e feedback idempotente."""

from __future__ import annotations

import hashlib
from uuid import uuid4


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _seed_hypothesis(
    pool,
    *,
    publish: bool = True,
    evaluation_status: str = "generated",
    run_status: str = "completed",
    evidence_offset: str = "0 minutes",
) -> tuple[int, int]:
    manifest = _hash(str(uuid4()))
    dedup = _hash(f"dedup:{manifest}")
    lineage = _hash(f"lineage:{manifest}")
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO detect.manifest (manifest_hash, payload, code_version)"
            " VALUES (%s, '{}'::jsonb, 'test')",
            (manifest,),
        )
        cur.execute(
            """
            INSERT INTO etl.execucoes
              (worker, status, finalizado_em, linhas_processadas)
            VALUES ('silver_gold', 'sucesso', clock_timestamp(), 1)
            RETURNING execucao_id
            """
        )
        execution_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO etl.gold_checkpoint
              (etl_execution_id, ready_through, source_lsn)
            VALUES (%s, sim.now(), 10)
            RETURNING checkpoint_id
            """,
            (execution_id,),
        )
        checkpoint_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO detect.run (
              detector, params, checkpoint_id, manifest_hash, sim_now, status,
              claimed_by, lease_expires_at, heartbeat_at, fencing_token,
              attempt, input_lsn, input_digest, input_rows, stream_key,
              started_at, finished_at
            ) VALUES (
              'test', '{}'::jsonb, %s, %s, sim.now(), %s,
              'test', clock_timestamp() + interval '1 minute', clock_timestamp(),
              nextval('detect.fencing_token_seq'), 1, 10, %s, 1, 'live',
              clock_timestamp(), clock_timestamp()
            ) RETURNING run_id
            """,
            (checkpoint_id, manifest, run_status, _hash("input")),
        )
        run_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO gold.hypothesis_run_stats
              (run_id, input_rows, anomalies, candidates_prefiltered,
               candidates_evaluated, generated, duration_ms)
            VALUES (%s, 1, 1, 1, 1, 1, 25)
            """,
            (run_id,),
        )
        cur.execute(
            """
            INSERT INTO gold.source_quality_run (run_id, window_start, window_end)
            VALUES (%s, sim.now() - interval '15 minutes', sim.now())
            """,
            (run_id,),
        )
        cur.execute(
            """
            INSERT INTO gold.source_quality (
              source, run_id, expected_cadence, last_observation_at,
              freshness, completeness, validity, consistency, quality_score,
              status, expected_buckets, observed_buckets
            ) VALUES (
              'prometheus', %s, interval '15 minutes', sim.now(),
              1, 1, 1, 1, 1, 'healthy', 1, 1
            )
            """,
            (run_id,),
        )
        cur.execute(
            """
            INSERT INTO gold.hypothesis (
              run_id, family, kind, title, summary, scope,
              effect_start, effect_end, score, coverage, confidence,
              evaluation_status, dedup_key, lineage_key, revision
            ) VALUES (
              %s, 'backend_internal', 'operational', 'Falha interna',
              'Erro corroborado', '{"service":"playback"}'::jsonb,
              sim.now() - interval '5 minutes', sim.now(), 82, 0.9, 'high',
              %s, %s, %s, 1
            ) RETURNING hypothesis_id
            """,
            (run_id, evaluation_status, dedup, lineage),
        )
        hypothesis_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO gold.hypothesis_feature (
              hypothesis_id, feature, applicability, value, weight,
              contribution, explanation
            ) VALUES (%s, 'A', 'available', 0.9, 0.25, 0.225, 'desvio')
            """,
            (hypothesis_id,),
        )
        cur.execute(
            """
            INSERT INTO gold.hypothesis_evidence (
              hypothesis_id, role, polarity, source, entity, metric,
              event_at, available_at, strength, quality, explanation
            ) VALUES (
              %s, 'subject', 'favorable', 'prometheus', 'playback',
              'error_rate_pct', sim.now(), sim.now() + %s::interval,
              0.9, 1, 'erro alto'
            )
            """,
            (hypothesis_id, evidence_offset),
        )
        if publish:
            cur.execute(
                """
                INSERT INTO gold.manifest_publication_event
                  (manifest_hash, action, gate_metrics)
                VALUES (%s, 'published', '{"test":true}'::jsonb)
                """,
                (manifest,),
            )
    return run_id, hypothesis_id


def test_hipotese_gerada_aparece_sem_publicacao(client, pool):
    run_id, hypothesis_id = _seed_hypothesis(pool, publish=False)
    runs = client.get("/api/v1/hypothesis-runs").json["items"]
    hypotheses = client.get("/api/v1/hypotheses").json["items"]
    assert [item["run_id"] for item in runs] == [run_id]
    assert [item["hypothesis_id"] for item in hypotheses] == [hypothesis_id]

    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.manifest_publication_event
              (manifest_hash, action, gate_metrics)
            SELECT manifest_hash, 'withdrawn', '{}'::jsonb
              FROM detect.run WHERE run_id = %s
            """,
            (run_id,),
        )

    runs = client.get("/api/v1/hypothesis-runs").json["items"]
    hypotheses = client.get("/api/v1/hypotheses").json["items"]
    assert [item["run_id"] for item in runs] == [run_id]
    assert [item["hypothesis_id"] for item in hypotheses] == [hypothesis_id]


def test_detalhe_e_feedback_idempotente(client, pool):
    _, hypothesis_id = _seed_hypothesis(pool)
    detail = client.get(f"/api/v1/hypotheses/{hypothesis_id}")
    assert detail.status_code == 200
    assert detail.json["manifest"] == {}
    assert detail.json["features"][0]["feature"] == "A"
    assert detail.json["evidence"][0]["source"] == "prometheus"
    assert detail.json["source_quality"][0]["status"] == "healthy"

    key = str(uuid4())
    payload = {
        "verdict": "confirmed",
        "note": "confirmado no incidente",
        "reviewer_ref": "plantao",
        "idempotency_key": key,
    }
    created = client.post(f"/api/v1/hypotheses/{hypothesis_id}/feedback", json=payload)
    replay = client.post(f"/api/v1/hypotheses/{hypothesis_id}/feedback", json=payload)
    assert created.status_code == 201
    assert replay.status_code == 200
    assert created.json["feedback_id"] == replay.json["feedback_id"]
    assert created.json["reviewer_verified"] is False

    conflict = client.post(
        f"/api/v1/hypotheses/{hypothesis_id}/feedback",
        json={**payload, "verdict": "rejected"},
    )
    assert conflict.status_code == 409


def test_feedback_valida_payload_e_limite(client, pool):
    _, hypothesis_id = _seed_hypothesis(pool)
    response = client.post(
        f"/api/v1/hypotheses/{hypothesis_id}/feedback",
        json={"verdict": "talvez", "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 422

    oversized = client.post(
        f"/api/v1/hypotheses/{hypothesis_id}/feedback",
        data=b"x" * 4097,
        content_type="application/json",
    )
    assert oversized.status_code == 413


def test_papel_da_api_nao_le_tabela_base(pool):
    _seed_hypothesis(pool)
    with pool.connection() as conn:
        conn.execute("SET ROLE argus_reader")
        assert conn.execute("SELECT count(*) FROM gold.v_hypothesis").fetchone()[0] == 1
        try:
            conn.execute("SELECT count(*) FROM gold.hypothesis")
        except Exception as error:
            assert getattr(error, "sqlstate", None) == "42501"
            conn.rollback()
        finally:
            conn.execute("RESET ROLE")


def test_view_esconde_avaliacoes_que_nao_geraram_hipotese(client, pool):
    """`discarded` e `insufficient_evidence` ficam so nas tabelas internas."""
    for status in ("discarded", "insufficient_evidence"):
        _, hypothesis_id = _seed_hypothesis(pool, evaluation_status=status)
        listagem = client.get("/api/v1/hypotheses").json["items"]
        assert hypothesis_id not in [item["hypothesis_id"] for item in listagem]
        assert client.get(f"/api/v1/hypotheses/{hypothesis_id}").status_code == 404

    # Controle: o mesmo cenario com `generated` aparece.
    _, publicada = _seed_hypothesis(pool)
    listagem = client.get("/api/v1/hypotheses").json["items"]
    assert publicada in [item["hypothesis_id"] for item in listagem]


def test_view_esconde_run_que_ainda_nao_concluiu(client, pool):
    """Run `running` e trabalho em curso, nao resultado publicavel."""
    run_id, hypothesis_id = _seed_hypothesis(pool, run_status="running")
    assert client.get("/api/v1/hypothesis-runs").json["items"] == []
    assert client.get("/api/v1/hypotheses").json["items"] == []
    assert client.get(f"/api/v1/hypotheses/{hypothesis_id}").status_code == 404

    with pool.connection() as conn:
        conn.execute("UPDATE detect.run SET status = 'completed' WHERE run_id = %s", (run_id,))
    assert [item["run_id"] for item in client.get("/api/v1/hypothesis-runs").json["items"]] == [
        run_id
    ]


def test_view_de_evidencia_esconde_o_que_e_posterior_ao_sim_now(pool):
    """Evidencia com `available_at > run.sim_now` nunca sai pela view."""
    _, futura = _seed_hypothesis(pool, evidence_offset="30 minutes")
    _, presente = _seed_hypothesis(pool, evidence_offset="-1 minutes")
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM gold.v_hypothesis_evidence WHERE hypothesis_id = %s",
            (futura,),
        )
        assert cur.fetchone()[0] == 0
        cur.execute(
            "SELECT count(*) FROM gold.v_hypothesis_evidence WHERE hypothesis_id = %s",
            (presente,),
        )
        assert cur.fetchone()[0] == 1
        # A linha existe na tabela base: a view esconde, nao apaga.
        cur.execute(
            "SELECT count(*) FROM gold.hypothesis_evidence WHERE hypothesis_id = %s",
            (futura,),
        )
        assert cur.fetchone()[0] == 1


def test_papel_da_api_nao_alcanca_nenhuma_tabela_base(pool):
    """O GRANT e so nas views e na funcao de feedback."""
    _seed_hypothesis(pool)
    proibidas = (
        "gold.hypothesis",
        "gold.hypothesis_evidence",
        "gold.hypothesis_feedback",
        "detect.anomaly",
        "detect.run",
        "silver.analysis_fact_version",
    )
    with pool.connection() as conn:
        conn.execute("SET ROLE argus_reader")
        try:
            for tabela in proibidas:
                try:
                    conn.execute(f"SELECT count(*) FROM {tabela}")
                except Exception as error:
                    assert getattr(error, "sqlstate", None) == "42501", tabela
                    conn.rollback()
                else:
                    raise AssertionError(f"{tabela} ficou legivel pelo papel da API")
        finally:
            conn.execute("RESET ROLE")
