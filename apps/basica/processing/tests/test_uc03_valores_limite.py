"""Analise de valor limite e pos-condicoes do UC03."""

from __future__ import annotations

import datetime as dt
import inspect
import json
import logging
import os
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from argus_common import Metrics
from psycopg.errors import CheckViolation

from argus_processing import __main__ as processing_main
from argus_processing import etl, scoring
from argus_processing.analysis_repository import (
    claim_and_capture,
    persist_result,
    promote_manifest,
    register_manifest,
)
from argus_processing.analysisctl import FAMILIES
from argus_processing.catalog import Catalog
from argus_processing.domain import (
    AnalysisResult,
    Anomaly,
    Evidence,
    Fact,
    Feature,
    Hypothesis,
    SourceQuality,
)
from argus_processing.orchestration import iniciar_trabalho
from argus_processing.rules import Candidate, evaluate_candidates

NOW = dt.datetime(2026, 7, 12, 15, tzinfo=dt.UTC)


def _fact(serial: int = 1) -> Fact:
    """Cria um fato minimo e unico para uma candidata."""
    return Fact(
        fact_key=f"uc03-fact-{serial}",
        version_lsn=serial,
        role="subject",
        kind="metric",
        event_start=NOW + dt.timedelta(seconds=serial),
        event_end=None,
        available_at=NOW + dt.timedelta(seconds=serial),
        source="newrelic",
        entity=f"playback-{serial}",
        metric="error_rate_pct",
        dimension_type=None,
        dimension_value=None,
        value=5.0,
        sample_size=1_000,
        attributes={},
    )


def _anomaly(fact: Fact) -> Anomaly:
    """Cria a deteccao que origina a candidata."""
    return Anomaly(
        fact=fact,
        observed=5.0,
        expected=1.0,
        direction="up",
        deviation=4.0,
        z=5.0,
        strength=0.9,
        baseline_snapshot={"n": 12},
    )


def _quality() -> tuple[SourceQuality, ...]:
    """Mantem a fonte saudavel nos testes que variam outra condicao."""
    return (
        SourceQuality(
            source="newrelic",
            expected_cadence_seconds=900,
            last_observation_at=NOW,
            freshness=1.0,
            completeness=1.0,
            validity=1.0,
            consistency=1.0,
            quality_score=1.0,
            status="healthy",
            expected_buckets=1,
            observed_buckets=1,
        ),
    )


def _candidate(
    serial: int = 1,
    *,
    required_missing: tuple[str, ...] = (),
    contradiction: float = 0.0,
) -> tuple[Candidate, Anomaly]:
    """Cria uma candidata e permite variar ausencia e contradicao."""
    fact = _fact(serial)
    contrary = (
        (
            Evidence(
                role="optional",
                polarity="contrary",
                explanation="evidencia contraria sintetica",
                strength=contradiction,
            ),
        )
        if contradiction
        else ()
    )
    candidate = Candidate(
        family="backend_internal",
        kind="operational",
        anomaly_index=0,
        subject=fact,
        supporting=(),
        required_missing=required_missing,
        contrary=contrary,
        scope={"service": fact.entity},
        title="Possivel falha interna",
        summary="Candidata sintetica para a fronteira do UC03.",
    )
    return candidate, _anomaly(fact)


def _evaluation_status(
    monkeypatch,
    *,
    score: float,
    coverage: float,
    required_missing: tuple[str, ...] = (),
    contradiction: float = 0.0,
) -> str:
    """Avalia a classificacao real injetando apenas os fatores calculados."""
    candidate, anomaly = _candidate(
        required_missing=required_missing,
        contradiction=contradiction,
    )

    def fixed_score(_values, *, contradiction):
        return score, coverage, "low", ()

    monkeypatch.setattr("argus_processing.rules.score_features", fixed_score)
    hypotheses, *_ = evaluate_candidates((candidate,), (anomaly,), _quality(), Catalog())
    return hypotheses[0].evaluation_status


@pytest.mark.parametrize(
    ("score", "coverage", "expected"),
    [
        pytest.param(39.99, 0.50, "discarded", id="score-imediatamente-abaixo"),
        pytest.param(40.00, 0.50, "generated", id="score-no-limite"),
        pytest.param(40.01, 0.50, "generated", id="score-imediatamente-acima"),
        pytest.param(40.00, 0.49, "discarded", id="cobertura-imediatamente-abaixo"),
        pytest.param(40.00, 0.50, "generated", id="cobertura-no-limite"),
        pytest.param(40.00, 0.51, "generated", id="cobertura-imediatamente-acima"),
    ],
)
def test_a1_limites_de_geracao(monkeypatch, score, coverage, expected):
    status = _evaluation_status(monkeypatch, score=score, coverage=coverage)
    assert status == expected


@pytest.mark.parametrize(
    ("target_score", "expected"),
    [
        pytest.param(79.99, "medium", id="abaixo"),
        pytest.param(80.00, "high", id="no-limite"),
        pytest.param(80.01, "high", id="acima"),
    ],
)
def test_limite_de_score_para_confianca_alta(target_score, expected):
    other_value = (target_score / 100 - 0.05 * 0.70) / 0.95
    values = {
        name: ("available", 0.70 if name == "Q" else other_value, "teste")
        for name in scoring.WEIGHTS
    }
    score, coverage, confidence, _ = scoring.score_features(values, contradiction=0.0)
    assert score == pytest.approx(target_score)
    assert coverage == 1.0
    assert confidence == expected


@pytest.mark.parametrize(
    ("target_coverage", "expected"),
    [
        pytest.param(0.79, "medium", id="abaixo"),
        pytest.param(0.80, "high", id="no-limite"),
        pytest.param(0.81, "high", id="acima"),
    ],
)
def test_limite_de_cobertura_para_confianca_alta(monkeypatch, target_coverage, expected):
    monkeypatch.setattr(
        scoring,
        "WEIGHTS",
        {"A": target_coverage, "C": 1.0 - target_coverage},
    )
    values = {
        "A": ("available", 1.0, "forca disponivel"),
        "C": ("unavailable", None, "corroboracao indisponivel"),
        "Q": ("available", 0.70, "qualidade no limite"),
    }
    score, coverage, confidence, _ = scoring.score_features(values, contradiction=0.0)
    assert score == 100.0
    assert coverage == pytest.approx(target_coverage)
    assert confidence == expected


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        pytest.param(0.69, "medium", id="abaixo"),
        pytest.param(0.70, "high", id="no-limite"),
        pytest.param(0.71, "high", id="acima"),
    ],
)
def test_limite_de_qualidade_para_confianca_alta(quality, expected):
    values = {
        name: ("available", quality if name == "Q" else 1.0, "teste")
        for name in scoring.WEIGHTS
    }
    score, coverage, confidence, _ = scoring.score_features(values, contradiction=0.0)
    assert score >= 80.0
    assert coverage == 1.0
    assert confidence == expected


def test_a2_evidencia_obrigatoria_ausente_prevalece_sobre_score(monkeypatch):
    status = _evaluation_status(
        monkeypatch,
        score=100,
        coverage=1.0,
        required_missing=("evidencia obrigatoria",),
    )
    assert status == "insufficient_evidence"


def test_a3_contradicao_determinante_prevalece_sobre_score(monkeypatch):
    values = {name: ("available", 1.0, "teste") for name in scoring.WEIGHTS}
    for contradiction, expected_confidence in (
        (0.49, "high"),
        (0.50, "medium"),
        (0.51, "medium"),
    ):
        score, coverage, confidence, _ = scoring.score_features(
            values, contradiction=contradiction
        )
        assert score >= 80.0
        assert coverage == 1.0
        assert confidence == expected_confidence

    status = _evaluation_status(
        monkeypatch,
        score=100,
        coverage=1.0,
        contradiction=0.80,
    )
    assert status == "discarded"


@pytest.fixture
def uc03_execution(db, inserir_change):
    """Captura um fato persistido para testar a passagem da avaliacao ao banco."""
    event_at = db.sim_now() - dt.timedelta(hours=3)
    with db.connection() as conn:
        inserir_change(
            conn,
            "signal_bucket",
            {
                "bts": int(event_at.timestamp() * 1000),
                "source": "newrelic",
                "entity": "playback",
                "metric": "error_rate_pct",
                "value": 5.0,
            },
        )
        conn.execute("SELECT bronze.merge_todas()")
    assert etl.executar_bronze_silver(db, batch_size=100)["status"] == "sucesso"
    assert (
        etl.executar_silver_gold(db, janela_max_segundos=999_999_999)["status"]
        == "sucesso"
    )
    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")
    captured = claim_and_capture(
        db, worker_id="worker-uc03", manifest_hash=catalog.manifest_hash
    )
    assert captured is not None
    assert iniciar_trabalho(db, captured.claim)
    assert len(captured.facts) == 1
    fact = captured.facts[0]
    candidate, _ = _candidate()
    candidate = replace(candidate, subject=fact, scope={"service": fact.entity})
    quality = (replace(_quality()[0], last_observation_at=fact.available_at),)
    return catalog, captured, candidate, _anomaly(fact), quality


def _evaluated_result(candidate, anomaly, quality, catalog):
    """Usa o avaliador real e conserva suas estatisticas para a persistencia."""
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        (candidate,), (anomaly,), quality, catalog
    )
    return AnalysisResult(
        anomalies=(anomaly,),
        finding_anomalies=(anomaly,),
        baseline_updates={},
        quality=quality,
        hypotheses=hypotheses,
        candidates_prefiltered=prefiltered,
        candidates_evaluated=evaluated,
        candidates_truncated=truncated,
    )


def test_a3_descarte_preserva_justificativa_no_banco(db, uc03_execution):
    catalog, captured, candidate, anomaly, quality = uc03_execution
    contrary = Evidence(
        role="optional",
        polarity="contrary",
        explanation="contradicao determinante do cenario sintetico",
        strength=0.80,
    )
    candidate = replace(candidate, contrary=(contrary,))
    result = _evaluated_result(candidate, anomaly, quality, catalog)
    hypothesis = result.hypotheses[0]
    assert hypothesis.score >= 40
    assert hypothesis.coverage >= 0.50
    assert hypothesis.evaluation_status == "discarded"
    assert hypothesis.contradiction_strength == 0.80
    assert contrary in hypothesis.evidence

    persist_result(db, captured, result, duration_ms=1)
    persisted = db.fetch_all(
        """
        SELECT h.evaluation_status, h.contradiction_strength,
               e.role, e.polarity, e.strength, e.explanation
          FROM gold.hypothesis h
          JOIN gold.hypothesis_evidence e ON e.hypothesis_id = h.hypothesis_id
         WHERE h.run_id = %s AND e.polarity = 'contrary'
        """,
        (captured.claim.run_id,),
    )
    assert persisted == [
        {
            "evaluation_status": "discarded",
            "contradiction_strength": 0.80,
            "role": "optional",
            "polarity": "contrary",
            "strength": 0.80,
            "explanation": contrary.explanation,
        }
    ]


def test_a1_hipotese_so_fica_visivel_apos_publicacao_do_manifesto(db, uc03_execution):
    catalog, captured, candidate, anomaly, quality = uc03_execution
    result = _evaluated_result(candidate, anomaly, quality, catalog)
    assert result.hypotheses[0].evaluation_status == "generated"
    persist_result(db, captured, result, duration_ms=1)
    run_id = captured.claim.run_id
    hypothesis = db.fetch_one(
        "SELECT hypothesis_id FROM gold.hypothesis WHERE run_id = %s", (run_id,)
    )
    assert hypothesis is not None
    assert (
        db.fetch_all(
            "SELECT hypothesis_id FROM gold.v_hypothesis WHERE run_id = %s", (run_id,)
        )
        == []
    )
    assert (
        db.fetch_all(
            "SELECT action FROM gold.manifest_publication_event WHERE manifest_hash = %s",
            (catalog.manifest_hash,),
        )
        == []
    )

    # A promocao e explicita: este teste nao avalia os criterios da CLI do portao.
    promote_manifest(db, catalog.manifest_hash, {"test": True})
    assert db.fetch_all(
        "SELECT action FROM gold.manifest_publication_event WHERE manifest_hash = %s",
        (catalog.manifest_hash,),
    ) == [{"action": "published"}]
    assert db.fetch_all(
        "SELECT hypothesis_id FROM gold.v_hypothesis WHERE run_id = %s", (run_id,)
    ) == [hypothesis]


@pytest.mark.parametrize("published", [False, True], ids=["sombra", "publicado"])
def test_e4_falha_na_persistencia_nao_expoe_hipotese_parcial(
    db, uc03_execution, published
):
    catalog, captured, candidate, anomaly, quality = uc03_execution
    if published:
        promote_manifest(db, catalog.manifest_hash, {"test": True})
    events_before = db.fetch_all(
        """
        SELECT publication_event_id, action FROM gold.manifest_publication_event
         WHERE manifest_hash = %s ORDER BY publication_event_id
        """,
        (catalog.manifest_hash,),
    )
    result = _evaluated_result(candidate, anomaly, quality, catalog)
    assert result.hypotheses[0].evaluation_status == "generated"
    # A estatistica e gravada depois de anomalias, hipoteses, fatores e evidencias.
    # Sua restricao provoca uma falha real de SQL no fim da mesma transacao.
    with pytest.raises(CheckViolation) as error:
        persist_result(
            db, captured, replace(result, candidates_evaluated=-1), duration_ms=1
        )
    assert error.value.diag.table_name == "hypothesis_run_stats"
    run_id = captured.claim.run_id
    assert db.fetch_one(
        "SELECT status, finished_at FROM detect.run WHERE run_id = %s", (run_id,)
    ) == {"status": "running", "finished_at": None}
    assert (
        db.fetch_one(
            "SELECT count(*) AS n FROM detect.anomaly WHERE run_id = %s", (run_id,)
        )["n"]
        == 0
    )
    assert (
        db.fetch_one(
            "SELECT count(*) AS n FROM gold.hypothesis WHERE run_id = %s", (run_id,)
        )["n"]
        == 0
    )
    assert db.fetch_one("SELECT count(*) AS n FROM gold.hypothesis_feature")["n"] == 0
    assert db.fetch_one("SELECT count(*) AS n FROM gold.hypothesis_evidence")["n"] == 0
    assert (
        db.fetch_one(
            "SELECT count(*) AS n FROM gold.hypothesis_run_stats WHERE run_id = %s",
            (run_id,),
        )["n"]
        == 0
    )
    assert (
        db.fetch_all(
            "SELECT run_id FROM gold.v_hypothesis_run WHERE run_id = %s", (run_id,)
        )
        == []
    )
    assert (
        db.fetch_all(
            "SELECT hypothesis_id FROM gold.v_hypothesis WHERE run_id = %s", (run_id,)
        )
        == []
    )
    assert (
        db.fetch_all(
            """
            SELECT publication_event_id, action FROM gold.manifest_publication_event
             WHERE manifest_hash = %s ORDER BY publication_event_id
            """,
            (catalog.manifest_hash,),
        )
        == events_before
    )
    assert len(events_before) == int(published)


def test_e2_limite_de_500_hipoteses_geradas(monkeypatch):
    candidates: list[Candidate] = []
    anomalies: list[Anomaly] = []
    for serial in range(1, 502):
        candidate, anomaly = _candidate(serial)
        candidate = Candidate(
            family=candidate.family,
            kind=candidate.kind,
            anomaly_index=len(anomalies),
            subject=candidate.subject,
            supporting=candidate.supporting,
            required_missing=candidate.required_missing,
            contrary=candidate.contrary,
            scope=candidate.scope,
            title=candidate.title,
            summary=candidate.summary,
        )
        candidates.append(candidate)
        anomalies.append(anomaly)

    def maximum_score(_values, *, contradiction):
        return 100.0, 1.0, "high", ()

    monkeypatch.setattr("argus_processing.rules.score_features", maximum_score)
    for quantity, expected_generated, expected_truncated in (
        (499, 499, 0),
        (500, 500, 0),
        (501, 500, 1),
    ):
        hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
            candidates[:quantity],
            tuple(anomalies[:quantity]),
            _quality(),
            Catalog(),
        )
        assert prefiltered == quantity
        assert evaluated == quantity
        assert (
            sum(item.evaluation_status == "generated" for item in hypotheses)
            == expected_generated
        )
        assert truncated == expected_truncated


def test_e2_tetos_documentados_sao_os_defaults_do_motor():
    parameters = inspect.signature(evaluate_candidates).parameters
    assert parameters["max_total"].default == 10_000
    assert parameters["max_per_family"].default == 2_000
    assert parameters["max_generated"].default == 500


@pytest.mark.parametrize("quantity", [500, 501], ids=["no-limite", "acima"])
def test_e2_motor_persiste_truncamento_e_cli_decide_promocao(
    db, database_url, uc03_execution, quantity
):
    catalog, captured, candidate, anomaly, quality = uc03_execution
    families = sorted(FAMILIES)
    # Escopos sinteticos distintos evitam deduplicacao. As onze familias estao
    # presentes para que somente o truncamento possa reprovar o portao.
    candidates = tuple(
        replace(
            candidate,
            family=families[index % len(families)],
            kind="data_quality"
            if families[index % len(families)] == "source_data_delay"
            else "context"
            if families[index % len(families)] == "expected_live_peak"
            else "operational",
            scope={"source": "newrelic", "service": "playback", "cenario": index},
        )
        for index in range(quantity)
    )
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, (anomaly,), quality, catalog
    )
    assert prefiltered == evaluated == quantity
    assert len(hypotheses) == quantity
    assert sum(item.evaluation_status == "generated" for item in hypotheses) == 500
    assert truncated == quantity - 500
    result = AnalysisResult(
        anomalies=(anomaly,),
        finding_anomalies=(anomaly,),
        baseline_updates={},
        quality=quality,
        hypotheses=hypotheses,
        candidates_prefiltered=prefiltered,
        candidates_evaluated=evaluated,
        candidates_truncated=truncated,
    )
    persist_result(db, captured, result, duration_ms=1)
    assert db.fetch_one(
        """
        SELECT candidates_evaluated, candidates_truncated, generated, discarded,
               truncated
          FROM gold.hypothesis_run_stats WHERE run_id = %s
        """,
        (captured.claim.run_id,),
    ) == {
        "candidates_evaluated": quantity,
        "candidates_truncated": quantity - 500,
        "generated": 500,
        "discarded": quantity - 500,
        "truncated": quantity > 500,
    }
    assert db.fetch_all("SELECT action FROM gold.manifest_publication_event") == []
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "argus_processing.analysisctl",
            "evaluate-and-promote",
            "--precision-at-5",
            "0.70",
            "--api-p95-ms",
            "900",
            "--api-max-ms",
            "2500",
            "--checkpoint-sla-ok",
            "--suite-ok",
        ],
        env={**os.environ, "DATABASE_URL": database_url, "IMAGE_TAG": "test"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.stderr == ""
    metrics = json.loads(completed.stdout)
    assert metrics["families_observed"] == families
    assert metrics["completed_runs"] == 1
    assert metrics["truncated_runs"] == int(quantity > 500)
    assert metrics["failures"] == (["ha runs truncados"] if quantity > 500 else [])
    assert completed.returncode == (2 if quantity > 500 else 0)
    events = db.fetch_all(
        """
        SELECT action, gate_metrics FROM gold.manifest_publication_event
         WHERE manifest_hash = %s
        """,
        (catalog.manifest_hash,),
    )
    assert events == (
        [] if quantity > 500 else [{"action": "published", "gate_metrics": metrics}]
    )
    assert db.fetch_one(
        "SELECT count(*) AS n FROM gold.v_hypothesis WHERE run_id = %s",
        (captured.claim.run_id,),
    )["n"] == (0 if quantity > 500 else 500)


def test_e1_catalogo_invalido_registra_erro_sem_publicar(tmp_path, db, database_url):
    catalogs = tmp_path / "catalogs"
    catalogs.mkdir()
    (catalogs / "sources.json").write_text("{invalido", encoding="utf-8")
    # O subprocesso conserva os logs e sinais reais sem alterar o pytest.
    # Somente o diretorio de entrada do catalogo e substituido.
    startup = """
import sys
from pathlib import Path
from unittest.mock import patch
from argus_processing.__main__ import main

with patch("argus_processing.catalog.importlib.resources.files",
           return_value=Path(sys.argv[1])):
    raise SystemExit(main())
"""
    completed = subprocess.run(
        [sys.executable, "-c", startup, str(tmp_path)],
        env={
            **os.environ,
            "DATABASE_URL": database_url,
            "ANALYSIS_ENABLED": "true",
            "LOG_LEVEL": "INFO",
            "SERVICE_NAME": "argus-processing-uc03",
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 1
    assert completed.stderr == ""
    records = [json.loads(line) for line in completed.stdout.splitlines()]
    errors = [record for record in records if record["level"] == "ERROR"]
    assert len(errors) == 1
    assert errors[0]["logger"] == "argus-processing-uc03"
    assert errors[0]["message"] == "processamento abortou"
    assert "JSONDecodeError" in errors[0]["exception"]
    assert "Expecting property name enclosed in double quotes" in errors[0]["exception"]
    assert not any("worker" in record["message"] for record in records)

    assert db.fetch_one("SELECT count(*) AS n FROM detect.run")["n"] == 0
    assert db.fetch_one("SELECT count(*) AS n FROM detect.manifest")["n"] == 0
    assert (
        db.fetch_one("SELECT count(*) AS n FROM gold.manifest_publication_event")["n"]
        == 0
    )


def test_e1_manifesto_invalido_registra_erro_sem_publicar(db, checkpoint, caplog):
    catalog = Catalog("test")
    catalog.manifest_hash = "0" * 64
    shutdown = SimpleNamespace(running=True)

    def stop_after_cycle(_seconds):
        shutdown.running = False

    # Controla apenas a duracao do laco, mantendo analise, banco e logging reais.
    shutdown.sleep = stop_after_cycle
    with caplog.at_level(logging.ERROR, logger="argus_processing.__main__"):
        processing_main._laco_analise(
            db,
            shutdown,
            Metrics("Argus/Test", "analysis"),
            catalog,
            worker_id="worker-manifesto-invalido",
            intervalo_segundos=0,
            lease_segundos=120,
            heartbeat_segundos=30,
            max_input_rows=250_000,
            max_candidates=10_000,
            max_candidates_family=2_000,
            max_generated=500,
            code_version="test",
        )
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].getMessage() == "worker de analise: erro no ciclo"
    assert errors[0].exc_info[0] is ValueError
    assert str(errors[0].exc_info[1]) == (
        "manifest_hash does not match the canonical payload"
    )

    assert db.fetch_one("SELECT count(*) AS n FROM detect.run")["n"] == 0
    assert db.fetch_one("SELECT count(*) AS n FROM detect.manifest")["n"] == 0
    assert (
        db.fetch_one("SELECT count(*) AS n FROM gold.manifest_publication_event")["n"]
        == 0
    )


def test_pos_condicao_gerada_nao_significa_causa_confirmada(monkeypatch):
    status = _evaluation_status(monkeypatch, score=65, coverage=0.70)
    assert status == "generated"
    assert status != "confirmed"


def _hypothesis(status: str, score: float, token: str, effect_at: dt.datetime):
    """Monta uma hipotese completa para exercitar a persistencia existente."""
    return Hypothesis(
        family="backend_internal",
        kind="operational",
        title=f"Hipotese {status}",
        summary="Cenario sintetico de pos-condicao.",
        scope={"service": f"playback-{token}"},
        effect_start=effect_at,
        effect_end=effect_at,
        score=score,
        coverage=0.9,
        confidence="high" if score >= 80 else "medium",
        evaluation_status=status,
        contradiction_strength=0.0,
        dedup_key=token.upper() * 64,
        lineage_key=token * 64,
        features=(Feature("A", "available", 0.9, 0.25, 0.225, "forca"),),
        evidence=(Evidence("subject", "favorable", "serie degradada"),),
    )


def test_pos_condicao_persiste_estados_metadados_e_sem_confirmacao(db, checkpoint):
    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")
    captured = claim_and_capture(
        db, worker_id="worker-pos-condicao", manifest_hash=catalog.manifest_hash
    )
    assert captured is not None
    assert captured.claim.checkpoint_id == checkpoint["checkpoint_id"]
    assert iniciar_trabalho(db, captured.claim)

    hypotheses = (
        _hypothesis("generated", 65.0, "a", captured.claim.sim_now),
        _hypothesis("discarded", 39.99, "b", captured.claim.sim_now),
        _hypothesis("insufficient_evidence", 85.0, "f", captured.claim.sim_now),
    )
    result = AnalysisResult(
        anomalies=(),
        finding_anomalies=(),
        baseline_updates={},
        quality=(),
        hypotheses=hypotheses,
        candidates_prefiltered=3,
        candidates_evaluated=3,
        candidates_truncated=0,
    )
    persist_result(db, captured, result, duration_ms=1)

    persisted = db.fetch_all(
        """
        SELECT h.evaluation_status, h.score, h.coverage, h.confidence,
               h.run_id, r.manifest_hash,
               count(DISTINCT f.feature) AS features,
               count(DISTINCT e.evidence_id) AS evidence
          FROM gold.hypothesis h
          JOIN detect.run r ON r.run_id = h.run_id
          JOIN detect.manifest m ON m.manifest_hash = r.manifest_hash
          LEFT JOIN gold.hypothesis_feature f
            ON f.hypothesis_id = h.hypothesis_id
          LEFT JOIN gold.hypothesis_evidence e
            ON e.hypothesis_id = h.hypothesis_id
         GROUP BY h.hypothesis_id, r.manifest_hash
         ORDER BY h.evaluation_status
        """
    )
    assert {
        row["evaluation_status"]: (row["score"], row["coverage"], row["confidence"])
        for row in persisted
    } == {
        "generated": (65.0, 0.9, "medium"),
        "discarded": (39.99, 0.9, "medium"),
        "insufficient_evidence": (85.0, 0.9, "high"),
    }
    assert all(row["run_id"] == captured.claim.run_id for row in persisted)
    assert all(row["manifest_hash"] == catalog.manifest_hash for row in persisted)
    assert all(row["features"] == 1 and row["evidence"] == 1 for row in persisted)
    assert db.fetch_one("SELECT count(*) AS n FROM gold.hypothesis_feedback")["n"] == 0
