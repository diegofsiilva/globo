"""Detector EWMA circadiano estritamente causal."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from zoneinfo import ZoneInfo

from argus_processing.catalog import Catalog, MetricPolicy
from argus_processing.domain import Anomaly, Baseline, Fact


def _transform(value: float, policy: MetricPolicy) -> float:
    return math.log1p(max(value, 0.0)) if policy.transform == "log1p" else value


def _inverse(value: float, policy: MetricPolicy) -> float:
    return math.expm1(value) if policy.transform == "log1p" else value


def _material(observed: float, expected: float, policy: MetricPolicy) -> bool:
    absolute = abs(observed - expected)
    relative = absolute / max(abs(expected), 1e-12)
    return (
        absolute >= policy.materiality_absolute
        and relative >= policy.materiality_relative
    )


def _bad_direction(observed: float, expected: float, policy: MetricPolicy) -> bool:
    if policy.direction == "up":
        return observed > expected
    if policy.direction == "down":
        return observed < expected
    return observed != expected


def detect(
    facts: Iterable[Fact],
    baselines: Mapping[tuple[str, str, str, int], Baseline],
    catalog: Catalog,
    *,
    alpha: float = 0.20,
    min_samples: int = 12,
    z_threshold: float = 3.5,
) -> tuple[tuple[Anomaly, ...], dict[tuple[str, str, str, int], Baseline]]:
    """Avalia subjects em ordem causal e devolve estado novo sem mutar a entrada."""
    state = {
        key: Baseline(value.mean, value.variance, value.n, value.last_event_at)
        for key, value in baselines.items()
    }
    anomalies: list[Anomaly] = []

    subjects = sorted(
        (f for f in facts if f.role == "subject" and f.kind == "metric"),
        key=lambda f: (f.event_start, f.source, f.entity, f.metric, f.fact_key),
    )
    for fact in subjects:
        if fact.value is None or not math.isfinite(fact.value):
            continue
        policy = catalog.metric(fact.metric)
        if policy is None:
            continue
        # O container roda em UTC; converter explicitamente sem depender do TZ
        # do processo.
        hour_brt = fact.event_start.astimezone(ZoneInfo("America/Sao_Paulo")).hour
        key = (fact.source, fact.entity, fact.metric, hour_brt)
        baseline = state.setdefault(key, Baseline())

        # Um update atrasado mais velho que o estado nao pode ser avaliado com
        # um baseline que ja contem o futuro dele. Ele permanece como contexto
        # para revisoes, mas nao inicia outra anomalia.
        if (
            baseline.last_event_at is not None
            and fact.event_start <= baseline.last_event_at
        ):
            continue

        transformed = _transform(fact.value, policy)
        old_mean = baseline.mean
        old_variance = baseline.variance
        if old_mean is not None and baseline.n >= min_samples:
            sigma = max(
                math.sqrt(max(old_variance or 0.0, 0.0)),
                policy.sigma_floor,
                0.05 * abs(old_mean),
            )
            z = (transformed - old_mean) / sigma
            expected = _inverse(old_mean, policy)
            if (
                abs(z) >= z_threshold
                and _bad_direction(fact.value, expected, policy)
                and _material(fact.value, expected, policy)
            ):
                direction = (
                    policy.direction
                    if policy.direction != "two_sided"
                    else ("up" if fact.value > expected else "down")
                )
                anomalies.append(
                    Anomaly(
                        fact=fact,
                        observed=fact.value,
                        expected=expected,
                        direction=direction,
                        deviation=fact.value - expected,
                        z=z,
                        strength=min(abs(z) / 6.0, 1.0),
                        baseline_snapshot={
                            "mean_transformed": old_mean,
                            "variance_transformed": old_variance,
                            "n": baseline.n,
                            "transform": policy.transform,
                            "sigma_effective": sigma,
                        },
                    )
                )

        if old_mean is None:
            baseline.mean = transformed
            baseline.variance = 0.0
        else:
            delta = transformed - old_mean
            baseline.mean = (1.0 - alpha) * old_mean + alpha * transformed
            baseline.variance = (1.0 - alpha) * (
                (old_variance or 0.0) + alpha * delta * delta
            )
        baseline.n += 1
        baseline.last_event_at = fact.event_start

    return tuple(anomalies), state
