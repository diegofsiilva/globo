"""Cenarios das onze familias e suas protecoes deterministicas."""

from __future__ import annotations

import datetime as dt
from itertools import count

from argus_processing.catalog import Catalog
from argus_processing.domain import Anomaly, Fact, SourceQuality
from argus_processing.rules import build_candidates, evaluate_candidates

NOW = dt.datetime(2026, 7, 12, 15, tzinfo=dt.UTC)
_IDS = count(1)


def _fact(
    source: str,
    entity: str,
    metric: str,
    value: float = 5,
    *,
    minutes: int = 0,
    sample_size: int | None = 1000,
    dimension_type: str | None = None,
    dimension_value: str | None = None,
    kind: str = "metric",
    event_end: dt.datetime | None = None,
    attributes: dict | None = None,
) -> Fact:
    serial = next(_IDS)
    at = NOW + dt.timedelta(minutes=minutes)
    return Fact(
        fact_key=f"fact-{serial}",
        version_lsn=serial,
        role="subject" if kind == "metric" else "context",
        kind=kind,
        event_start=at,
        event_end=event_end,
        available_at=at,
        source=source,
        entity=entity,
        metric=metric,
        dimension_type=dimension_type,
        dimension_value=dimension_value,
        value=value,
        sample_size=sample_size,
        attributes=attributes or {},
    )


def _anomaly(fact: Fact, *, direction: str = "up", strength: float = 0.9) -> Anomaly:
    return Anomaly(
        fact=fact,
        observed=fact.value or 0,
        expected=1,
        direction=direction,
        deviation=(fact.value or 0) - 1,
        z=5.4,
        strength=strength,
        baseline_snapshot={"n": 12},
    )


def _quality(source: str, status: str = "healthy", score: float = 1.0) -> SourceQuality:
    return SourceQuality(
        source=source,
        expected_cadence_seconds=900,
        last_observation_at=NOW,
        freshness=score,
        completeness=score,
        validity=1,
        consistency=1,
        quality_score=score,
        status=status,
        expected_buckets=1,
        observed_buckets=0 if status == "silent" else 1,
        details={"evaluated_at": NOW.isoformat()},
    )


def _evaluate_family(
    family: str,
    anomalies: tuple[Anomaly, ...],
    facts: tuple[Fact, ...],
    qualities: tuple[SourceQuality, ...],
):
    catalog = Catalog()
    candidates = [
        item
        for item in build_candidates(anomalies, facts, qualities, catalog)
        if item.family == family
    ]
    hypotheses, *_ = evaluate_candidates(candidates, anomalies, qualities, catalog)
    return candidates, hypotheses


def test_as_onze_familias_formam_candidatos_em_cenarios_positivos():
    deploy_effect = _fact("newrelic", "playback", "error_rate_pct")
    deploy = _fact("tsuru", "playback-api", "app.deploy", minutes=-5, kind="context")
    playback = _fact(
        "rpaas",
        "playback.video.globo.com",
        "4xx_rate_pct",
        sample_size=100,
    )
    cdn = _fact("cdn_live_errors", "globo-rj", "errors")
    origin = _fact("origin_live_errors", "globo-rj", "errors", minutes=-1)
    geo = _fact(
        "npaw_geo",
        "RJ",
        "error_rate_pct",
        4,
        sample_size=500,
        dimension_type="uf",
        dimension_value="RJ",
    )
    geo_peer = _fact(
        "npaw_geo",
        "SP",
        "error_rate_pct",
        1,
        sample_size=500,
        dimension_type="uf",
        dimension_value="SP",
    )
    waf = _fact("cloudarmor", "playback", "blocked_rps", 100)
    player = _fact(
        "npaw_player",
        "player-bad",
        "error_rate_pct",
        4,
        sample_size=200,
        dimension_type="player",
        dimension_value="player-bad",
    )
    player_peer = _fact(
        "npaw_player",
        "player-ok",
        "error_rate_pct",
        1,
        sample_size=200,
        dimension_type="player",
        dimension_value="player-ok",
    )
    qoe = _fact("prometheus", "qoe-service", "latency_ms_avg", 300)
    normal_error = _fact("apollo", "qoe-service", "error_rate_pct", 0.1)
    volume = _fact("npaw_live_active", "globo-rj", "active_sessions", 5000)
    event = _fact(
        "editorial",
        "globo",
        "live_event",
        kind="context",
        event_end=NOW + dt.timedelta(hours=2),
    )
    live_error = _fact("apollo", "globo-rj", "error_rate_pct", 0.1)
    live_qoe = _fact("npaw_live_qoe", "globo-rj", "jointime_s_avg", 1)

    anomaly_facts = (deploy_effect, playback, cdn, origin, geo, waf, player, qoe, volume)
    anomalies = tuple(_anomaly(item) for item in anomaly_facts)
    facts = anomaly_facts + (
        deploy,
        geo_peer,
        player_peer,
        normal_error,
        event,
        live_error,
        live_qoe,
    )
    qualities = tuple(_quality(source) for source in {item.source for item in facts}) + (
        _quality("missing-source", "silent", 0),
    )
    families = {
        item.family for item in build_candidates(anomalies, facts, qualities, Catalog())
    }
    assert families == {
        "deploy_regression",
        "backend_internal",
        "playback_authorization",
        "cdn_degradation",
        "origin_encoding",
        "regional_or_isp",
        "waf_block",
        "player_or_device",
        "qoe_without_error",
        "expected_live_peak",
        "source_data_delay",
    }


def test_causalidade_invalida_descarta_origem_waf_e_contexto_ao_vivo():
    origin = _fact("origin_live_errors", "globo-rj", "errors")
    downstream_before = _fact("cdn_live_errors", "globo-rj", "errors", minutes=-5)
    candidates, hypotheses = _evaluate_family(
        "origin_encoding",
        (_anomaly(origin), _anomaly(downstream_before)),
        (origin, downstream_before),
        (_quality("origin_live_errors"), _quality("cdn_live_errors")),
    )
    assert candidates and hypotheses[0].evaluation_status == "discarded"

    waf = _fact("cloudarmor", "playback", "blocked_rps")
    error_before = _fact("prometheus", "playback", "error_rate_pct", minutes=-5)
    _, hypotheses = _evaluate_family(
        "waf_block",
        (_anomaly(waf), _anomaly(error_before)),
        (waf, error_before),
        (_quality("cloudarmor"), _quality("prometheus")),
    )
    assert hypotheses[0].evaluation_status == "discarded"

    volume = _fact("npaw_live_active", "globo-rj", "active_sessions", 5000)
    event = _fact(
        "editorial",
        "globo",
        "live_event",
        kind="context",
        event_end=NOW + dt.timedelta(hours=1),
    )
    bad_qoe = _fact("npaw_live_qoe", "globo-rj", "jointime_s_avg", 8)
    normal_error = _fact("apollo", "globo-rj", "error_rate_pct", 0.1)
    _, hypotheses = _evaluate_family(
        "expected_live_peak",
        (_anomaly(volume), _anomaly(bad_qoe)),
        (volume, event, bad_qoe, normal_error),
        tuple(_quality(source) for source in ("npaw_live_active", "npaw_live_qoe")),
    )
    assert hypotheses[0].evaluation_status == "discarded"


def test_evidencia_required_indisponivel_fica_insufficient_e_nao_contraria():
    regional = _fact(
        "npaw_geo",
        "RJ",
        "error_rate_pct",
        4,
        sample_size=100,
        dimension_type="uf",
        dimension_value="RJ",
    )
    peer = _fact(
        "npaw_geo",
        "SP",
        "error_rate_pct",
        1,
        sample_size=500,
        dimension_type="uf",
        dimension_value="SP",
    )
    _, hypotheses = _evaluate_family(
        "regional_or_isp",
        (_anomaly(regional),),
        (regional, peer),
        (_quality("npaw_geo"),),
    )
    assert hypotheses[0].evaluation_status == "insufficient_evidence"
    assert hypotheses[0].contradiction_strength == 0

    qoe = _fact("prometheus", "playback", "latency_ms_avg", 300)
    _, hypotheses = _evaluate_family(
        "qoe_without_error",
        (_anomaly(qoe),),
        (qoe,),
        (_quality("prometheus"),),
    )
    assert hypotheses[0].evaluation_status == "insufficient_evidence"


def test_rpaas_4xx_isolado_nao_vira_backend_e_delay_e_deterministico():
    rpaas = _fact(
        "rpaas",
        "playback.video.globo.com",
        "4xx_rate_pct",
        sample_size=100,
    )
    _, hypotheses = _evaluate_family(
        "backend_internal",
        (_anomaly(rpaas),),
        (rpaas,),
        (_quality("rpaas"),),
    )
    assert hypotheses[0].evaluation_status == "discarded"

    delayed = (_quality("prometheus", "silent", 0),)
    candidates, first = _evaluate_family("source_data_delay", (), (), delayed)
    _, second = _evaluate_family("source_data_delay", (), (), delayed)
    assert candidates and first[0].evaluation_status == "generated"
    assert first[0].dedup_key == second[0].dedup_key
    assert first[0].effect_start == NOW


def test_relacao_semantica_e_corte_sao_estaveis():
    effect = _fact("prometheus", "playback", "error_rate_pct")
    unrelated = _fact("tsuru", "billing", "app.deploy", minutes=-5, kind="context")
    future = _fact("tsuru", "playback", "app.deploy", minutes=5, kind="context")
    candidates, _ = _evaluate_family(
        "deploy_regression",
        (_anomaly(effect),),
        (effect, unrelated, future),
        (_quality("prometheus"), _quality("tsuru")),
    )
    assert candidates == []

    catalog = Catalog()
    base = build_candidates(
        (_anomaly(effect),),
        (effect,),
        (_quality("prometheus"),),
        catalog,
    )
    one = evaluate_candidates(
        base, (_anomaly(effect),), (_quality("prometheus"),), catalog
    )
    two = evaluate_candidates(
        reversed(base), (_anomaly(effect),), (_quality("prometheus"),), catalog
    )
    assert [item.dedup_key for item in one[0]] == [item.dedup_key for item in two[0]]
