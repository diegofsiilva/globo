"""Analise de valor limite e pos-condicoes do UC03."""

from __future__ import annotations

import datetime as dt
import inspect
import json
import logging
import math
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
from argus_processing.rules import Candidate, build_candidates, evaluate_candidates

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


@pytest.mark.parametrize(
    ("contradiction", "expected"),
    [
        pytest.param(0.79, "generated", id="abaixo"),
        pytest.param(0.80, "discarded", id="no-limite"),
        pytest.param(0.81, "discarded", id="acima"),
    ],
)
def test_a3_limite_de_contradicao_determinante(contradiction, expected):
    candidate, anomaly = _candidate(contradiction=contradiction)
    hypotheses, _, evaluated, truncated = evaluate_candidates(
        (candidate,), (anomaly,), _quality(), Catalog()
    )
    hypothesis = hypotheses[0]
    # O score e real e permanece suficiente nos tres casos: apenas a guarda
    # de contradicao pode causar o descarte, nao score, cobertura ou budget.
    assert hypothesis.score >= 40
    assert hypothesis.coverage >= 0.50
    assert hypothesis.contradiction_strength == contradiction
    penalty = next(feature for feature in hypothesis.features if feature.name == "X")
    assert penalty.contribution == pytest.approx(-30 * contradiction)
    assert hypothesis.evaluation_status == expected
    assert (evaluated, truncated) == (1, 0)


# Extremos fora da faixa (CT39-CT54). Os trios (limite, -1, +1) acima param a
# 0,01 de cada limiar; estes casos vao ate os pontos onde os dois clamps de
# `scoring.score_features` agem (L30, por feature; L40, no score final) e
# levam ao classificador de `rules.evaluate_candidates` valores que o scoring
# nunca produz, para registrar onde a validacao de faixa mora e onde nao mora.


@pytest.mark.parametrize(
    ("feature_value", "contradiction", "expected_score", "expected_confidence"),
    [
        pytest.param(0.25, 1.00, 0.0, "low", id="um-clamp-inferior"),
        pytest.param(1.00, 1.00, 70.0, "low", id="um-sem-clamp"),
        pytest.param(1.00, -0.01, 100.0, "high", id="negativa-clamp-superior"),
    ],
)
def test_extremos_de_contradicao(
    feature_value, contradiction, expected_score, expected_confidence
):
    """Contradicao nos extremos 1,0 e -0,01, alem dos trios em torno de 0,50 e 0,80.

    - ``um-clamp-inferior`` (CT39): contradicao 1,0 sobre base 25 daria -5; o
      clamp inferior de ``score_features`` segura o score em 0,0 e a confianca
      cai a ``low``.
    - ``um-sem-clamp`` (CT40): contradicao 1,0 sobre base 100 da 70,0: a
      penalidade maxima e -30 e o clamp so age quando a base e menor que 30.
      A confianca ainda e ``low``, porque contradicao >= 0,80 barra ``medium``.
    - ``negativa-clamp-superior`` (CT41): contradicao -0,01 (entrada invalida)
      somaria 0,3 a base 100; o clamp superior segura o score em 100,0 e a
      confianca fica ``high``, porque a guarda le a contradicao bruta.
    """
    values = {name: ("available", feature_value, "teste") for name in scoring.WEIGHTS}
    score, coverage, confidence, features = scoring.score_features(
        values, contradiction=contradiction
    )
    assert score == pytest.approx(expected_score)
    assert coverage == 1.0
    assert confidence == expected_confidence
    penalty = next(feature for feature in features if feature.name == "X")
    assert penalty.contribution == pytest.approx(-30 * contradiction)


@pytest.mark.parametrize(
    ("raw_value", "expected_normalized", "expected_score"),
    [
        pytest.param(1.00, 1.0, 100.0, id="um"),
        pytest.param(1.01, 1.0, 100.0, id="acima-de-um"),
        pytest.param(-0.01, 0.0, 0.0, id="negativa"),
    ],
)
def test_extremos_de_valor_de_feature(raw_value, expected_normalized, expected_score):
    """Valor de feature em 1,00, 1,01 e -0,01: o clamp por feature (L30 do scoring).

    - ``um`` (CT42): todas as features em 1,0 produzem score 100,0 sem clamp.
    - ``acima-de-um`` (CT43): 1,01 e normalizado a 1,0 antes de ponderar; o
      score continua 100,0 e o valor gravado na Feature e o normalizado.
    - ``negativa`` (CT44): -0,01 e normalizado a 0,0; contribuicao zero em
      todas as features e score 0,0, sem virar valor negativo.
    """
    values = {name: ("available", raw_value, "teste") for name in scoring.WEIGHTS}
    score, coverage, _, features = scoring.score_features(values, contradiction=0.0)
    assert score == pytest.approx(expected_score)
    assert coverage == 1.0
    for feature in features:
        if feature.name == "X":
            continue
        assert feature.value == expected_normalized
        assert feature.contribution == pytest.approx(feature.weight * expected_normalized)


@pytest.mark.parametrize(
    ("applicability", "expected_coverage"),
    [
        pytest.param("unavailable", 0.0, id="zero"),
        pytest.param("not_applicable", 1.0, id="nenhuma-aplicavel"),
    ],
)
def test_extremos_de_cobertura(applicability, expected_coverage):
    """Cobertura nos extremos que o scoring consegue produzir.

    - ``zero`` (CT45): todas as features aplicaveis e indisponiveis dao
      cobertura 0,0, score 0,0 e confianca ``low``; ausencia nao vira zero
      dentro do score, mas a cobertura registra que nada foi medido.
    - ``nenhuma-aplicavel`` (CT46): sem feature aplicavel, a cobertura e 1,0
      por convencao (nao ha o que cobrir) e o score continua 0,0 e ``low``.
    """
    values = {name: (applicability, None, "teste") for name in scoring.WEIGHTS}
    score, coverage, confidence, _ = scoring.score_features(values, contradiction=0.0)
    assert score == 0.0
    assert coverage == expected_coverage
    assert confidence == "low"


@pytest.mark.parametrize(
    ("quality", "expected"),
    [
        pytest.param(-0.01, "medium", id="negativa"),
        pytest.param(1.01, "high", id="acima-de-um"),
    ],
)
def test_extremos_de_qualidade(quality, expected):
    """Qualidade Q em -0,01 e 1,01, alem do trio em torno de 0,70.

    - ``negativa`` (CT47): Q=-0,01 e normalizado a 0,0 na feature, mas a guarda
      de confianca le o valor bruto; -0,01 < 0,70 impede ``high`` e o score 95
      com cobertura 1,0 cai em ``medium``.
    - ``acima-de-um`` (CT48): Q=1,01 e normalizado a 1,0 na feature e o valor
      bruto satisfaz a guarda; score 100,0 e ``high``.
    """
    values = {
        name: ("available", quality if name == "Q" else 1.0, "teste")
        for name in scoring.WEIGHTS
    }
    score, coverage, confidence, features = scoring.score_features(
        values, contradiction=0.0
    )
    q_feature = next(feature for feature in features if feature.name == "Q")
    assert q_feature.value == max(0.0, min(1.0, quality))
    assert score == pytest.approx(100.0 - 5.0 * (1.0 - q_feature.value))
    assert coverage == 1.0
    assert confidence == expected


@pytest.mark.parametrize(
    ("score", "coverage", "expected"),
    [
        pytest.param(100.00, 1.00, "generated", id="score-maximo"),
        pytest.param(100.01, 1.00, "generated", id="score-acima-do-maximo"),
        pytest.param(-0.01, 1.00, "discarded", id="score-negativo"),
        pytest.param(40.00, 0.00, "discarded", id="cobertura-zero"),
        pytest.param(40.00, -0.01, "discarded", id="cobertura-negativa"),
        pytest.param(40.00, 1.01, "generated", id="cobertura-acima-de-um"),
    ],
)
def test_a1_extremos_fora_da_faixa(monkeypatch, score, coverage, expected):
    """Classificador de A1 recebendo score e cobertura que o scoring nunca produz.

    O ``score_features`` e substituido por um valor fixo, como nos trios de
    ``test_a1_limites_de_geracao``, para observar so a decisao de
    ``rules.evaluate_candidates``. Ela e um limiar puro (score >= 40 e
    cobertura >= 0,50) e nao valida faixa: quem garante 0..100 e 0..1 e o
    scoring, e estes casos registram essa divisao de responsabilidade.

    - ``score-maximo`` (CT49): 100,00 e 1,00 geram.
    - ``score-acima-do-maximo`` (CT50): 100,01 tambem gera; nao ha rejeicao
      por excesso no classificador.
    - ``score-negativo`` (CT51): -0,01 e descartado, como qualquer valor
      abaixo de 40.
    - ``cobertura-zero`` (CT52): cobertura 0,00 descarta mesmo com score no
      limite.
    - ``cobertura-negativa`` (CT53): -0,01 descarta.
    - ``cobertura-acima-de-um`` (CT54): 1,01 gera; nao ha rejeicao por excesso.
    """
    status = _evaluation_status(monkeypatch, score=score, coverage=coverage)
    assert status == expected


@pytest.mark.parametrize(
    ("quantity", "expected_evaluated", "expected_truncated"),
    [(1999, 1999, 0), (2000, 2000, 0), (2001, 2000, 1)],
    ids=["abaixo", "no-limite", "acima"],
)
def test_e2_limite_real_de_2000_candidatas_por_familia(
    quantity, expected_evaluated, expected_truncated
):
    candidate, anomaly = _candidate(required_missing=("evidencia controlada ausente",))
    candidates = tuple(
        replace(candidate, scope={"cenario": index}) for index in range(quantity)
    )
    # A ausencia obrigatoria impede geracao e isola o corte por familia do teto
    # de 500 geradas. Nenhum limite ou calculo do motor e substituido.
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, (anomaly,), _quality(), Catalog()
    )
    assert (prefiltered, evaluated, truncated) == (
        quantity,
        expected_evaluated,
        expected_truncated,
    )
    assert len(hypotheses) == expected_evaluated
    assert len({item.dedup_key for item in hypotheses}) == expected_evaluated
    assert all(item.evaluation_status == "insufficient_evidence" for item in hypotheses)


@pytest.mark.parametrize(
    ("quantity", "expected_evaluated", "expected_truncated"),
    [(9999, 9999, 0), (10000, 10000, 0), (10001, 10000, 1)],
    ids=["abaixo", "no-limite", "acima"],
)
def test_e2_limite_real_de_10000_candidatas_totais(
    quantity, expected_evaluated, expected_truncated
):
    candidate, anomaly = _candidate(required_missing=("evidencia controlada ausente",))
    families = sorted(FAMILIES)
    candidates = tuple(
        replace(
            candidate, family=families[index % len(families)], scope={"cenario": index}
        )
        for index in range(quantity)
    )
    assert (
        max(sum(item.family == family for item in candidates) for family in families)
        < 2000
    )
    # As candidatas sao entradas sinteticas do avaliador. Distribui-las entre
    # familias isola o teto total; required_missing isola o teto de geradas.
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, (anomaly,), _quality(), Catalog()
    )
    assert (prefiltered, evaluated, truncated) == (
        quantity,
        expected_evaluated,
        expected_truncated,
    )
    assert len(hypotheses) == expected_evaluated
    assert len({item.dedup_key for item in hypotheses}) == expected_evaluated
    assert all(item.evaluation_status == "insufficient_evidence" for item in hypotheses)


def test_fluxo_principal_oito_passos_com_persistencia(db, inserir_change):
    # Passo 1: fotografia real; anomalias e qualidade sao entradas controladas
    # do UC02. Detector e canario ficam fora do escopo deste teste do UC03.
    event_at = db.sim_now() - dt.timedelta(hours=3)
    with db.connection() as conn:
        for source, entity, minutes in (
            ("newrelic", "playback", 0),
            ("apollo", "playback", -2),
            ("prometheus", "playback", -60),
            ("newrelic", "billing", 0),
        ):
            inserir_change(
                conn,
                "signal_bucket",
                {
                    "bts": int(
                        (event_at + dt.timedelta(minutes=minutes)).timestamp() * 1000
                    ),
                    "source": source,
                    "entity": entity,
                    "metric": "error_rate_pct",
                    "value": 5,
                },
            )
        inserir_change(
            conn,
            "rpaas_bucket",
            {
                "bucket_ts_ms": int(event_at.timestamp() * 1000),
                "region": "sudeste",
                "vhost": "playback.video.globo.com",
                "requests_total": 50,
                "requests_4xx": 5,
                "requests_5xx": 0,
            },
        )
        inserir_change(
            conn,
            "tsuru_event",
            {
                "start_time_ms": int(
                    (event_at - dt.timedelta(minutes=5)).timestamp() * 1000
                ),
                "uniqueid": "uc03-deploy",
                "target_type": "app",
                "target_value": "playback-api",
                "kind": "app.deploy",
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
        db, worker_id="uc03-fluxo", manifest_hash=catalog.manifest_hash
    )
    assert captured is not None
    assert iniciar_trabalho(db, captured.claim)
    assert len(captured.facts) == 8
    assert all(fact.available_at <= captured.claim.sim_now for fact in captured.facts)
    facts = {(fact.source, fact.entity, fact.metric): fact for fact in captured.facts}
    subject = facts["newrelic", "playback", "error_rate_pct"]
    support = facts["apollo", "playback", "error_rate_pct"]
    rpaas = facts["rpaas", "playback.video.globo.com", "4xx_rate_pct"]
    deploy = facts["tsuru", "playback-api", "app.deploy"]
    anomalies = tuple(
        replace(
            _anomaly(fact),
            strength=strength,
            observed=fact.value,
            deviation=fact.value - 1,
        )
        for fact, strength in ((subject, 0.9), (support, 0.6), (rpaas, 0.7))
    )
    quality = tuple(
        replace(_quality()[0], source=source, last_observation_at=event_at)
        for source in sorted({fact.source for fact in captured.facts})
    )

    # Passos 2 e 3: a mesma anomalia participa de mais de uma explicacao;
    # candidatas e associacoes sao formadas pelas regras reais.
    candidates = build_candidates(anomalies, captured.facts, quality, catalog)
    assert len(candidates) == 7
    assert {item.family for item in candidates} == {
        "backend_internal",
        "deploy_regression",
        "playback_authorization",
    }
    assert {item.family for item in candidates if item.anomaly_index == 0} == {
        "backend_internal",
        "deploy_regression",
    }
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, anomalies, quality, catalog
    )
    assert (prefiltered, evaluated, truncated) == (7, 7, 0)
    by_subject = {(item.family, item.anomaly_indexes[0]): item for item in hypotheses}
    backend = by_subject["backend_internal", 0]
    regression = by_subject["deploy_regression", 0]
    contrary = by_subject["backend_internal", 2]
    missing = by_subject["playback_authorization", 2]
    assert set(backend.anomaly_indexes) == {0, 1, 2}

    # Passo 4: fontes relacionadas corroboram; billing e o sinal de uma hora
    # antes nao entram. A contraria e a ausencia conservam polaridades distintas.
    assert {e.fact.fact_key for e in backend.evidence if e.fact} == {
        subject.fact_key,
        support.fact_key,
        rpaas.fact_key,
        facts["rpaas", "playback.video.globo.com", "5xx_rate_pct"].fact_key,
    }
    assert any(e.fact == deploy for e in regression.evidence)
    assert any(e.polarity == "contrary" and e.strength == 0.9 for e in contrary.evidence)
    assert any(
        e.polarity == "missing" and "100" in e.explanation for e in missing.evidence
    )
    assert missing.contradiction_strength == 0

    # Passo 5: oraculos numericos independentes para os seis fatores.
    factors = {feature.name: feature for feature in backend.features}
    assert set(factors) == {"A", "T", "C", "E", "I", "Q", "X"}
    assert factors["A"].value == 0.9
    assert factors["T"].applicability == "not_applicable"
    assert factors["C"].value == pytest.approx(0.856)
    assert factors["E"].value == 1
    assert factors["I"].applicability == "unavailable"
    assert factors["Q"].value == 1
    temporal = next(f for f in regression.features if f.name == "T")
    assert temporal.value == pytest.approx(2 ** (-5 / 15))
    impact = next(f for f in contrary.features if f.name == "I")
    assert impact.value == pytest.approx(math.log1p(50) / math.log1p(10000))

    # Passos 6 e 7: contribuições, penalidade, cobertura e classificacao real.
    assert factors["C"].contribution == pytest.approx(0.1712)
    assert backend.score == pytest.approx(100 * 0.5962 / 0.65)
    assert backend.coverage == pytest.approx(0.8125)
    assert backend.confidence == "high"
    penalty = next(f for f in contrary.features if f.name == "X")
    assert penalty.contribution == -27
    assert backend.evaluation_status == regression.evaluation_status == "generated"
    assert contrary.evaluation_status == "discarded"
    assert missing.evaluation_status == "insufficient_evidence"

    # Passo 8: prioridade por forca (0.9, 0.7, 0.6) e desempate estavel;
    # inverter a entrada nao altera a ordem, os scores ou as evidencias.
    assert [item.anomaly_indexes[0] for item in hypotheses] == [0, 0, 2, 2, 2, 1, 1]
    reversed_hypotheses, *_ = evaluate_candidates(
        tuple(reversed(candidates)), anomalies, quality, catalog
    )
    assert reversed_hypotheses == hypotheses
    result = AnalysisResult(
        anomalies=anomalies,
        finding_anomalies=anomalies,
        baseline_updates={},
        quality=quality,
        hypotheses=hypotheses,
        candidates_prefiltered=prefiltered,
        candidates_evaluated=evaluated,
        candidates_truncated=truncated,
    )
    persist_result(db, captured, result, duration_ms=1)
    run_id = captured.claim.run_id
    rows = db.fetch_all(
        """SELECT hypothesis_id, dedup_key, evaluation_status, score, coverage, confidence
             FROM gold.hypothesis WHERE run_id = %s""",
        (run_id,),
    )
    assert len(rows) == 7
    persisted = {row["dedup_key"]: row for row in rows}
    for hypothesis in hypotheses:
        row = persisted[hypothesis.dedup_key]
        assert (
            row["evaluation_status"],
            row["score"],
            row["coverage"],
            row["confidence"],
        ) == (
            hypothesis.evaluation_status,
            hypothesis.score,
            hypothesis.coverage,
            hypothesis.confidence,
        )
        saved_features = db.fetch_all(
            """SELECT feature, applicability, value, weight, contribution, explanation
                 FROM gold.hypothesis_feature
                WHERE hypothesis_id = %s ORDER BY feature""",
            (row["hypothesis_id"],),
        )
        assert saved_features == [
            {
                "feature": f.name,
                "applicability": f.applicability,
                "value": f.value,
                "weight": f.weight,
                "contribution": f.contribution,
                "explanation": f.explanation,
            }
            for f in sorted(hypothesis.features, key=lambda f: f.name)
        ]
        saved_evidence = db.fetch_all(
            """SELECT role, polarity, explanation, fact_key FROM gold.hypothesis_evidence
                WHERE hypothesis_id = %s ORDER BY evidence_id""",
            (row["hypothesis_id"],),
        )
        assert saved_evidence == [
            {
                "role": e.role,
                "polarity": e.polarity,
                "explanation": e.explanation,
                "fact_key": e.fact.fact_key if e.fact else None,
            }
            for e in hypothesis.evidence
        ]
    assert (
        db.fetch_one(
            """SELECT count(DISTINCT m.group_id) AS groups
             FROM gold.finding_group_member m
             JOIN detect.anomaly a ON a.anomaly_id = m.finding_id
            WHERE m.finding_kind = 'anomaly' AND a.run_id = %s AND a.fact_key = %s""",
            (run_id, subject.fact_key),
        )["groups"]
        >= 2
    )
    assert db.fetch_one(
        """SELECT candidates_prefiltered, candidates_evaluated, candidates_truncated,
                  generated, discarded, insufficient_evidence
             FROM gold.hypothesis_run_stats WHERE run_id = %s""",
        (run_id,),
    ) == {
        "candidates_prefiltered": 7,
        "candidates_evaluated": 7,
        "candidates_truncated": 0,
        "generated": 5,
        "discarded": 1,
        "insufficient_evidence": 1,
    }
    assert db.fetch_one(
        "SELECT status, manifest_hash FROM detect.run WHERE run_id = %s", (run_id,)
    ) == {"status": "completed", "manifest_hash": catalog.manifest_hash}
    assert db.fetch_one("SELECT count(*) AS n FROM gold.hypothesis_feedback")["n"] == 0
    # Desde a migration 032, o fim do fluxo basico ja deixa as geradas prontas
    # para revisao humana: a view expoe as cinco, e so elas, sem esperar a
    # publicacao do manifesto. Descartada e insuficiente ficam fora da leitura.
    generated_ids = {
        row["hypothesis_id"]
        for row in db.fetch_all(
            """SELECT hypothesis_id FROM gold.hypothesis
                WHERE run_id = %s AND evaluation_status = 'generated'""",
            (run_id,),
        )
    }
    assert len(generated_ids) == 5
    assert {
        row["hypothesis_id"]
        for row in db.fetch_all(
            "SELECT hypothesis_id FROM gold.v_hypothesis WHERE run_id = %s", (run_id,)
        )
    } == generated_ids
    # A publicacao continua explicita e auditavel; CT29 a exercita.
    assert db.fetch_all("SELECT action FROM gold.manifest_publication_event") == []


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


def test_a1_hipotese_gerada_fica_visivel_e_publicacao_fica_auditada(db, uc03_execution):
    catalog, captured, candidate, anomaly, quality = uc03_execution
    result = _evaluated_result(candidate, anomaly, quality, catalog)
    assert result.hypotheses[0].evaluation_status == "generated"
    persist_result(db, captured, result, duration_ms=1)
    run_id = captured.claim.run_id
    hypothesis = db.fetch_one(
        "SELECT hypothesis_id FROM gold.hypothesis WHERE run_id = %s", (run_id,)
    )
    assert hypothesis is not None
    # Regra da migration 032: visivel para revisao assim que o run conclui,
    # antes de qualquer evento de publicacao.
    assert db.fetch_all(
        "SELECT hypothesis_id FROM gold.v_hypothesis WHERE run_id = %s", (run_id,)
    ) == [hypothesis]
    assert (
        db.fetch_all(
            "SELECT action FROM gold.manifest_publication_event WHERE manifest_hash = %s",
            (catalog.manifest_hash,),
        )
        == []
    )

    # A promocao e explicita: este teste nao avalia os criterios da CLI do portao.
    # Ela grava o evento de auditoria e nao muda o que a leitura ja expunha.
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
    # A recusa do portao fica registrada (codigo 2, nenhum evento `published`),
    # mas nao esconde as 500 geradas: desde a migration 032 a publicacao e
    # auditoria, e o truncamento aparece em gold.hypothesis_run_stats.
    assert (
        db.fetch_one(
            "SELECT count(*) AS n FROM gold.v_hypothesis WHERE run_id = %s",
            (captured.claim.run_id,),
        )["n"]
        == 500
    )


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
