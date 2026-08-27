"""Contratos imutaveis do detector e do motor de hipoteses."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

Availability = Literal["available", "unavailable", "not_applicable"]


@dataclass(frozen=True, slots=True)
class Fact:
    fact_key: str
    version_lsn: int
    role: str
    kind: str
    event_start: dt.datetime
    event_end: dt.datetime | None
    available_at: dt.datetime
    source: str
    entity: str
    metric: str
    dimension_type: str | None
    dimension_value: str | None
    value: float | None
    sample_size: int | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Baseline:
    mean: float | None = None
    variance: float | None = None
    n: int = 0
    last_event_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class Anomaly:
    fact: Fact
    observed: float
    expected: float
    direction: str
    deviation: float
    z: float
    strength: float
    baseline_snapshot: dict[str, Any]
    persisted_id: int | None = None


@dataclass(frozen=True, slots=True)
class SourceQuality:
    source: str
    expected_cadence_seconds: int
    last_observation_at: dt.datetime | None
    freshness: float | None
    completeness: float | None
    validity: float | None
    consistency: float | None
    quality_score: float | None
    status: str
    expected_buckets: int
    observed_buckets: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Feature:
    name: str
    applicability: Availability
    value: float | None
    weight: float
    contribution: float | None
    explanation: str


@dataclass(frozen=True, slots=True)
class Evidence:
    role: str
    polarity: str
    explanation: str
    fact: Fact | None = None
    observed: float | None = None
    expected: float | None = None
    strength: float | None = None
    quality: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Hypothesis:
    family: str
    kind: str
    title: str
    summary: str
    scope: dict[str, Any]
    effect_start: dt.datetime
    effect_end: dt.datetime
    score: float
    coverage: float
    confidence: str
    evaluation_status: str
    contradiction_strength: float
    dedup_key: str
    lineage_key: str
    features: tuple[Feature, ...]
    evidence: tuple[Evidence, ...]
    anomaly_indexes: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    anomalies: tuple[Anomaly, ...]
    finding_anomalies: tuple[Anomaly, ...]
    baseline_updates: dict[tuple[str, str, str, int], Baseline]
    quality: tuple[SourceQuality, ...]
    hypotheses: tuple[Hypothesis, ...]
    candidates_prefiltered: int
    candidates_evaluated: int
    candidates_truncated: int
