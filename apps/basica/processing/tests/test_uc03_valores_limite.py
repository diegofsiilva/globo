"""Analise de valor limite e pos-condicoes do UC03."""

from __future__ import annotations

import datetime as dt
import inspect
import json

import pytest

from argus_processing import scoring
from argus_processing.analysis_repository import (
    claim_and_capture,
    persist_result,
    register_manifest,
)
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


def test_e1_catalogo_invalido_interrompe_o_motor(monkeypatch, tmp_path, db):
    catalogs = tmp_path / "catalogs"
    catalogs.mkdir()
    (catalogs / "sources.json").write_text("{invalido", encoding="utf-8")
    monkeypatch.setattr(
        "argus_processing.catalog.importlib.resources.files", lambda _: tmp_path
    )

    with pytest.raises(json.JSONDecodeError):
        Catalog()

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
