"""Propriedades causais do EWMA e do canario."""

from __future__ import annotations

import datetime as dt
import math

from argus_processing.catalog import Catalog
from argus_processing.detector import detect
from argus_processing.domain import Baseline, Fact
from argus_processing.quality import evaluate_quality


def _fact(
    *,
    value: float,
    at: dt.datetime,
    metric: str = "latency_ms_avg",
    role: str = "subject",
) -> Fact:
    return Fact(
        fact_key=f"{at.timestamp()}:{metric}:{value}",
        version_lsn=int(at.timestamp()),
        role=role,
        kind="metric",
        event_start=at,
        event_end=None,
        available_at=at,
        source="prometheus",
        entity="playback",
        metric=metric,
        dimension_type=None,
        dimension_value=None,
        value=value,
        sample_size=1000,
    )


def test_ewma_avalia_antes_de_atualizar_e_ignora_melhoria():
    catalog = Catalog()
    instant = dt.datetime(2026, 7, 12, 15, tzinfo=dt.UTC)  # 12h BRT
    key = ("prometheus", "playback", "latency_ms_avg", 12)
    initial = {
        key: Baseline(
            mean=math.log1p(100),
            variance=0.0,
            n=12,
            last_event_at=instant - dt.timedelta(days=1),
        )
    }

    anomalies, updated = detect((_fact(value=300, at=instant),), initial, catalog)
    assert len(anomalies) == 1
    assert round(anomalies[0].expected) == 100
    assert anomalies[0].baseline_snapshot["n"] == 12
    assert updated[key].n == 13

    improvements, _ = detect(
        (_fact(value=50, at=instant + dt.timedelta(days=1)),), initial, catalog
    )
    assert improvements == ()


def test_cold_start_atualiza_sem_gerar_anomalia():
    catalog = Catalog()
    start = dt.datetime(2026, 7, 1, 15, tzinfo=dt.UTC)
    facts = tuple(_fact(value=100, at=start + dt.timedelta(days=i)) for i in range(12))
    anomalies, baselines = detect(reversed(facts), {}, catalog)
    assert anomalies == ()
    assert next(iter(baselines.values())).n == 12


def test_fim_congelado_do_simulador_nao_cria_silencio_artificial():
    catalog = Catalog()
    start = dt.datetime(2026, 7, 12, 9, tzinfo=dt.UTC)
    simulator_end = start + dt.timedelta(minutes=30)
    facts = (
        _fact(value=100, at=start),
        _fact(value=100, at=start + dt.timedelta(minutes=15)),
        _fact(value=100, at=simulator_end),
    )
    quality = evaluate_quality(
        facts,
        catalog,
        window_start=start,
        window_end=start + dt.timedelta(hours=12),
        simulator_end=simulator_end,
    )
    prometheus = next(item for item in quality if item.source == "prometheus")
    assert prometheus.status != "silent"
    assert prometheus.last_observation_at == simulator_end
