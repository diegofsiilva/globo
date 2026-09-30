"""Confere que os dados congelados do benchmark reproduzem o motor Python."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import pytest

from argus_processing.catalog import Catalog
from argus_processing.detector import detect
from argus_processing.domain import Anomaly, Baseline, Fact, SourceQuality
from argus_processing.quality import evaluate_quality
from argus_processing.rules import build_candidates, evaluate_candidates

FIXTURES = Path(__file__).resolve().parents[1] / "benchmarks" / "fixtures"
RULE_CASES = json.loads((FIXTURES / "regras_casos_v1.json").read_text(encoding="utf-8"))
CYCLE_CASE = json.loads((FIXTURES / "ciclo_caso_v1.json").read_text(encoding="utf-8"))
WORKLOADS = json.loads((FIXTURES / "cargas_v1.json").read_text(encoding="utf-8"))


def _date(value: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if value is not None else None


def _facts(rows: list[dict[str, Any]]) -> tuple[Fact, ...]:
    return tuple(
        Fact(
            **{
                **row,
                "event_start": _date(row["event_start"]),
                "event_end": _date(row["event_end"]),
                "available_at": _date(row["available_at"]),
            }
        )
        for row in rows
    )


def _anomalies(
    rows: list[dict[str, Any]], facts: tuple[Fact, ...]
) -> tuple[Anomaly, ...]:
    by_key = {fact.fact_key: fact for fact in facts}
    return tuple(
        Anomaly(
            **{
                **{key: value for key, value in row.items() if key != "fact_key"},
                "fact": by_key[row["fact_key"]],
            }
        )
        for row in rows
    )


def _quality(rows: list[dict[str, Any]]) -> tuple[SourceQuality, ...]:
    return tuple(
        SourceQuality(**{**row, "last_observation_at": _date(row["last_observation_at"])})
        for row in rows
    )


def _baselines(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str, int], Baseline]:
    return {
        tuple(entry["key"]): Baseline(
            **{
                **entry["value"],
                "last_event_at": _date(entry["value"]["last_event_at"]),
            }
        )
        for entry in rows
    }


def _project_anomaly(item: Anomaly) -> dict[str, Any]:
    data = dataclasses.asdict(item)
    data["fact_key"] = data.pop("fact")["fact_key"]
    return data


def _project_candidate(item: Any) -> dict[str, Any]:
    data = dataclasses.asdict(item)
    subject = data.pop("subject")
    supporting = data.pop("supporting")
    data["subject_fact_key"] = subject["fact_key"] if subject else None
    data["supporting_fact_keys"] = [fact["fact_key"] for fact in supporting]
    for evidence in data["contrary"]:
        fact = evidence.pop("fact")
        evidence["fact_key"] = fact["fact_key"] if fact else None
        evidence["version_lsn"] = fact["version_lsn"] if fact else None
    return data


def _project_hypothesis(item: Any) -> dict[str, Any]:
    data = dataclasses.asdict(item)
    for evidence in data["evidence"]:
        fact = evidence.pop("fact")
        evidence["fact_key"] = fact["fact_key"] if fact else None
        evidence["version_lsn"] = fact["version_lsn"] if fact else None
    return data


def _json_ready(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            default=lambda item: (
                item.isoformat() if isinstance(item, dt.datetime) else str(item)
            ),
        )
    )


def _assert_parity(actual: Any, expected: Any) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        assert actual.keys() == expected.keys()
        for key in expected:
            _assert_parity(actual[key], expected[key])
    elif isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected, strict=True):
            _assert_parity(left, right)
    elif isinstance(expected, float):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool)
        assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12)
    else:
        assert actual == expected


def test_manifestos_cobrem_as_onze_familias_sem_ids_duplicados() -> None:
    assert {
        RULE_CASES["schema_version"],
        CYCLE_CASE["schema_version"],
        WORKLOADS["schema_version"],
    } == {1}
    assert len(RULE_CASES["cases"]) == 49
    assert {case["focus_family"] for case in RULE_CASES["cases"]} == set(
        Catalog().raw["rules.json"]
    )
    ids = [case["id"] for case in RULE_CASES["cases"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", RULE_CASES["cases"], ids=lambda case: case["id"])
def test_regras_conferem_com_referencia_congelada(case: dict[str, Any]) -> None:
    catalog = Catalog()
    assert catalog.manifest_hash == RULE_CASES["catalog_manifest_hash"]
    facts = _facts(case["facts"])
    anomalies = _anomalies(case["anomalies"], facts)
    quality = _quality(case["quality"])
    candidates = build_candidates(anomalies, facts, quality, catalog)
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, anomalies, quality, catalog
    )
    actual = {
        "candidates": [_project_candidate(item) for item in candidates],
        "candidates_prefiltered": prefiltered,
        "candidates_evaluated": evaluated,
        "candidates_truncated": truncated,
        "hypotheses": [_project_hypothesis(item) for item in hypotheses],
    }
    _assert_parity(_json_ready(actual), case["expected"])


def test_ciclo_completo_confere_com_referencia_congelada() -> None:
    catalog = Catalog()
    assert catalog.manifest_hash == CYCLE_CASE["catalog_manifest_hash"]
    case = CYCLE_CASE["case"]
    facts = _facts(case["facts"])
    baselines = _baselines(case["baselines"])
    quality = evaluate_quality(
        facts,
        catalog,
        window_start=_date(case["window_start"]),
        window_end=_date(case["window_end"]),
        simulator_end=_date(case["simulator_end"]),
    )
    anomalies, updates = detect(facts, baselines, catalog)
    candidates = build_candidates(anomalies, facts, quality, catalog)
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, anomalies, quality, catalog
    )
    actual = {
        "quality": [dataclasses.asdict(item) for item in quality],
        "anomalies": [_project_anomaly(item) for item in anomalies],
        "baseline_updates": [
            {"key": list(key), "value": dataclasses.asdict(value)}
            for key, value in sorted(updates.items())
        ],
        "candidates": [_project_candidate(item) for item in candidates],
        "candidates_prefiltered": prefiltered,
        "candidates_evaluated": evaluated,
        "candidates_truncated": truncated,
        "hypotheses": [_project_hypothesis(item) for item in hypotheses],
    }
    _assert_parity(_json_ready(actual), case["expected"])


@pytest.mark.parametrize(
    "workload", WORKLOADS["workloads"], ids=lambda workload: workload["id"]
)
def test_cargas_reproduzem_contagens_congeladas(workload: dict[str, Any]) -> None:
    catalog = Catalog()
    assert catalog.manifest_hash == WORKLOADS["catalog_manifest_hash"]
    facts = _facts(workload["facts"])
    baselines = _baselines(workload["baselines"])
    quality = evaluate_quality(
        facts,
        catalog,
        window_start=_date(workload["window_start"]),
        window_end=_date(workload["window_end"]),
        simulator_end=_date(workload["simulator_end"]),
    )
    anomalies, _ = detect(facts, baselines, catalog)
    candidates = build_candidates(anomalies, facts, quality, catalog)
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, anomalies, quality, catalog
    )
    actual = {
        "facts": len(facts),
        "anomalies": len(anomalies),
        "candidates_prefiltered": prefiltered,
        "candidates_evaluated": evaluated,
        "candidates_truncated": truncated,
        "hypotheses": len(hypotheses),
        "generated": sum(item.evaluation_status == "generated" for item in hypotheses),
        "insufficient_evidence": sum(
            item.evaluation_status == "insufficient_evidence" for item in hypotheses
        ),
        "discarded": sum(item.evaluation_status == "discarded" for item in hypotheses),
    }
    assert actual == workload["expected_counts"]
