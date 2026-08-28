"""Evidencia atrasada: latencia causal da NPAW e revisao append-only.

Duas propriedades do plano moram aqui e nao cabem nos testes de regra, porque
so aparecem quando ha DOIS checkpoints e o estado persistido de um alcanca o
outro:

1. uma fonte com latencia estrutural (NPAW/Youbora, 28 h) nao pode entrar na
   captura de um checkpoint cujo `sim_now` e anterior a `available_at`; e
2. uma evidencia que chega depois cria `revision + 1` apontando para a anterior,
   sem NUNCA reescrever a linha ja publicada.
"""

from __future__ import annotations

import datetime as dt

from argus_common import Metrics

from argus_processing import etl
from argus_processing.analysis_repository import (
    CapturedWork,
    claim_and_capture,
    persist_result,
    promote_manifest,
    register_manifest,
)
from argus_processing.catalog import Catalog
from argus_processing.domain import (
    AnalysisResult,
    Anomaly,
    Evidence,
    Feature,
    Hypothesis,
    SourceQuality,
)
from argus_processing.orchestration import iniciar_trabalho
from argus_processing.pipeline import analyze_once

# O evento da NPAW e velho o bastante para que `+28 h` caia ENTRE os dois
# checkpoints: invisivel no primeiro, disponivel no segundo.
NPAW_EVENT = dt.datetime(2026, 7, 11, 4, tzinfo=dt.UTC)
NPAW_AVAILABLE = NPAW_EVENT + dt.timedelta(hours=28)
PROMETHEUS_EVENT = dt.datetime(2026, 7, 12, 5, tzinfo=dt.UTC)
FIRST_CLOCK = dt.datetime(2026, 7, 12, 6, tzinfo=dt.UTC)
SECOND_CLOCK = dt.datetime(2026, 7, 12, 12, tzinfo=dt.UTC)

LINEAGE = "c" * 64


def _ms(value: dt.datetime) -> int:
    return int(value.timestamp() * 1000)


def _set_clock(db, instant: dt.datetime) -> None:
    with db.connection() as conn:
        conn.execute("SELECT sim.set_clock(%s, 1)", (instant,))


def _semear(db, inserir_change) -> None:
    """Um bucket Prometheus imediato e um bucket NPAW com 28 h de atraso."""
    _set_clock(db, FIRST_CLOCK)
    with db.connection() as conn:
        inserir_change(
            conn,
            "signal_bucket",
            {
                "bts": _ms(PROMETHEUS_EVENT),
                "source": "prometheus",
                "entity": "playback",
                "metric": "latency_ms_avg",
                "value": 100,
            },
        )
        inserir_change(
            conn,
            "player_hourly",
            {
                "hour_ts": _ms(NPAW_EVENT),
                "player": "player-x",
                "error_rate_pct": 5,
                "sessions": 500,
            },
            pk={"hour_ts": _ms(NPAW_EVENT), "player": "player-x"},
        )
        conn.execute("SELECT bronze.merge_todas()")
    assert etl.executar_bronze_silver(db, batch_size=1000)["status"] == "sucesso"
    assert (
        etl.executar_silver_gold(db, janela_max_segundos=999_999_999)["status"]
        == "sucesso"
    )


def test_npaw_so_entra_na_captura_28_horas_depois(db, inserir_change):
    """O fato existe na Silver desde o inicio, mas so e capturavel em +28 h."""
    _semear(db, inserir_change)

    disponibilidade = db.fetch_all(
        """
        SELECT DISTINCT source, event_start, available_at
          FROM silver.analysis_fact_version
         ORDER BY source
        """
    )
    assert disponibilidade == [
        {
            "source": "npaw_player",
            "event_start": NPAW_EVENT,
            "available_at": NPAW_AVAILABLE,
        },
        {
            "source": "prometheus",
            "event_start": PROMETHEUS_EVENT,
            "available_at": PROMETHEUS_EVENT + dt.timedelta(minutes=1),
        },
    ]

    catalog = Catalog("test")
    metrics = Metrics("Argus/Test", "analysis")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")

    primeiro = claim_and_capture(
        db, worker_id="worker-1", manifest_hash=catalog.manifest_hash
    )
    assert primeiro is not None
    assert primeiro.claim.sim_now < NPAW_AVAILABLE
    # O fato da NPAW ja esta na Silver, mas o run declarou um `sim_now` anterior
    # a `available_at`: capturar seria ler o futuro.
    assert {fact.source for fact in primeiro.facts} == {"prometheus"}

    iniciar_trabalho(db, primeiro.claim)
    persist_result(db, primeiro, _resultado_vazio(), duration_ms=1)

    # Segundo checkpoint, agora depois da disponibilidade da NPAW.
    _set_clock(db, SECOND_CLOCK)
    assert (
        etl.executar_silver_gold(db, janela_max_segundos=999_999_999)["status"]
        == "sucesso"
    )
    segundo = claim_and_capture(
        db, worker_id="worker-2", manifest_hash=catalog.manifest_hash
    )
    assert segundo is not None
    assert segundo.claim.checkpoint_id > primeiro.claim.checkpoint_id
    assert segundo.claim.sim_now >= NPAW_AVAILABLE
    assert "npaw_player" in {fact.source for fact in segundo.facts}

    # Nenhuma evidencia pode ser posterior ao `sim_now` do proprio run.
    assert all(fact.available_at <= segundo.claim.sim_now for fact in segundo.facts)
    assert metrics is not None


def _resultado_vazio() -> AnalysisResult:
    return AnalysisResult(
        anomalies=(),
        finding_anomalies=(),
        baseline_updates={},
        quality=(),
        hypotheses=(),
        candidates_prefiltered=0,
        candidates_evaluated=0,
        candidates_truncated=0,
    )


def _qualidade(source: str, status: str = "healthy") -> SourceQuality:
    return SourceQuality(
        source=source,
        expected_cadence_seconds=900,
        last_observation_at=NPAW_AVAILABLE,
        freshness=1.0,
        completeness=1.0,
        validity=1.0,
        consistency=1.0,
        quality_score=1.0,
        status=status,
        expected_buckets=1,
        observed_buckets=1,
        details={"evaluated_at": NPAW_AVAILABLE.isoformat()},
    )


def _hipotese(
    *,
    family: str,
    kind: str,
    score: float,
    lineage: str,
    dedup: str,
    anomaly_indexes: tuple[int, ...],
    scope: dict,
) -> Hypothesis:
    return Hypothesis(
        family=family,
        kind=kind,
        title=f"{family} em teste",
        summary="cenario sintetico de revisao",
        scope=scope,
        effect_start=PROMETHEUS_EVENT,
        effect_end=PROMETHEUS_EVENT,
        score=score,
        coverage=0.9,
        confidence="high" if score >= 80 else "medium",
        evaluation_status="generated",
        contradiction_strength=0.0,
        dedup_key=dedup,
        lineage_key=lineage,
        features=(
            Feature(
                name="A",
                applicability="available",
                value=0.9,
                weight=0.25,
                contribution=0.225,
                explanation="forca da anomalia",
            ),
        ),
        evidence=(
            Evidence(
                role="subject",
                polarity="favorable",
                explanation="serie degradada",
            ),
        ),
        anomaly_indexes=anomaly_indexes,
    )


def _resultado_com_revisao(
    captured: CapturedWork, *, score: float, dedup: str
) -> AnalysisResult:
    """Uma hipotese de qualidade ANTES de uma hipotese com anomalia.

    A ordem importa: e exatamente ela que quebrava quando o commit reaproveitava
    o nome `finding_id` (funcao) para guardar o id sintetico do finding de
    qualidade, transformando a funcao em int para a hipotese seguinte.
    """
    fato = captured.facts[0]
    anomalia = Anomaly(
        fact=fato,
        observed=500.0,
        expected=100.0,
        direction="up",
        deviation=400.0,
        z=5.0,
        strength=0.83,
        baseline_snapshot={"n": 12},
    )
    qualidade = _hipotese(
        family="source_data_delay",
        kind="data_quality",
        score=70,
        lineage="d" * 64,
        dedup="e" * 64,
        anomaly_indexes=(),
        scope={"source": "npaw_player"},
    )
    operacional = _hipotese(
        family="backend_internal",
        kind="operational",
        score=score,
        lineage=LINEAGE,
        dedup=dedup,
        anomaly_indexes=(0,),
        scope={"entity": fato.entity, "source": fato.source},
    )
    return AnalysisResult(
        anomalies=(anomalia,),
        finding_anomalies=(anomalia,),
        baseline_updates={},
        quality=(_qualidade("npaw_player"), _qualidade("prometheus")),
        hypotheses=(qualidade, operacional),
        candidates_prefiltered=2,
        candidates_evaluated=2,
        candidates_truncated=0,
    )


def test_evidencia_tardia_cria_revisao_sem_alterar_a_anterior(db, inserir_change):
    """`revision + 1` aponta para a anterior e a view expoe so a mais recente."""
    _semear(db, inserir_change)
    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")

    primeiro = claim_and_capture(
        db, worker_id="worker-1", manifest_hash=catalog.manifest_hash
    )
    assert primeiro is not None
    iniciar_trabalho(db, primeiro.claim)
    persist_result(
        db,
        primeiro,
        _resultado_com_revisao(primeiro, score=62, dedup="a" * 64),
        duration_ms=1,
    )

    original = db.fetch_one(
        """
        SELECT hypothesis_id, revision, score, confidence, supersedes_hypothesis_id
          FROM gold.hypothesis
         WHERE lineage_key = %s
        """,
        (LINEAGE,),
    )
    assert original["revision"] == 1
    assert original["supersedes_hypothesis_id"] is None

    _set_clock(db, SECOND_CLOCK)
    assert (
        etl.executar_silver_gold(db, janela_max_segundos=999_999_999)["status"]
        == "sucesso"
    )
    segundo = claim_and_capture(
        db, worker_id="worker-2", manifest_hash=catalog.manifest_hash
    )
    assert segundo is not None
    iniciar_trabalho(db, segundo.claim)
    persist_result(
        db,
        segundo,
        _resultado_com_revisao(segundo, score=88, dedup="b" * 64),
        duration_ms=1,
    )

    revisoes = db.fetch_all(
        """
        SELECT hypothesis_id, revision, score, confidence, supersedes_hypothesis_id
          FROM gold.hypothesis
         WHERE lineage_key = %s
         ORDER BY revision
        """,
        (LINEAGE,),
    )
    assert len(revisoes) == 2
    # A revisao 1 continua byte a byte como foi publicada.
    assert revisoes[0] == original
    assert revisoes[1]["revision"] == 2
    assert revisoes[1]["score"] == 88
    assert revisoes[1]["confidence"] == "high"
    assert revisoes[1]["supersedes_hypothesis_id"] == original["hypothesis_id"]

    promote_manifest(db, catalog.manifest_hash, {"test": True})
    publicadas = db.fetch_all(
        "SELECT hypothesis_id, revision FROM gold.v_hypothesis WHERE lineage_key = %s",
        (LINEAGE,),
    )
    assert publicadas == [{"hypothesis_id": revisoes[1]["hypothesis_id"], "revision": 2}]


def test_hipotese_de_qualidade_nao_quebra_finding_de_anomalia_no_mesmo_run(
    db, inserir_change
):
    """Regressao: a hipotese com anomalia vem DEPOIS da de qualidade no run."""
    _semear(db, inserir_change)
    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")
    captured = claim_and_capture(
        db, worker_id="worker-1", manifest_hash=catalog.manifest_hash
    )
    assert captured is not None
    iniciar_trabalho(db, captured.claim)
    persist_result(
        db,
        captured,
        _resultado_com_revisao(captured, score=88, dedup="a" * 64),
        duration_ms=1,
    )

    findings = db.fetch_all(
        """
        SELECT h.family, f.finding_kind, f.role
          FROM gold.hypothesis h
          JOIN gold.hypothesis_finding f ON f.hypothesis_id = h.hypothesis_id
         WHERE h.run_id = %s
         ORDER BY h.family, f.finding_kind
        """,
        (captured.claim.run_id,),
    )
    assert findings == [
        {"family": "backend_internal", "finding_kind": "anomaly", "role": "subject"},
        {
            "family": "source_data_delay",
            "finding_kind": "source_quality",
            "role": "subject",
        },
    ]


def test_replay_do_mesmo_checkpoint_nao_gera_segundo_run_concluido(db, inserir_change):
    """Mesmo checkpoint + mesmo manifesto = uma unica conclusao."""
    _semear(db, inserir_change)
    catalog = Catalog("test")
    metrics = Metrics("Argus/Test", "analysis")
    assert analyze_once(db, metrics, catalog, worker_id="worker-1", code_version="test")
    # Sem checkpoint novo nao ha trabalho: o run anterior ja concluiu.
    assert not analyze_once(
        db, metrics, catalog, worker_id="worker-2", code_version="test"
    )
    concluidos = db.fetch_one(
        """
        SELECT count(*) AS n
          FROM detect.run
         WHERE manifest_hash = %s AND status = 'completed'
        """,
        (catalog.manifest_hash,),
    )
    assert concluidos["n"] == 1


def test_ground_truth_nunca_entra_como_entrada_de_analise(db, inserir_change):
    """Incidentes e rotulos sao gabarito de avaliacao, nunca insumo do score.

    Eles continuam sendo materializados na Gold (`incident_window`) para medir
    precision offline, mas nao podem virar `analysis_fact_version` nem entrar
    em `run_input_fact` -- se entrassem, o detector "acertaria" usando a
    resposta.
    """
    _semear(db, inserir_change)
    inicio = int(PROMETHEUS_EVENT.timestamp() * 1000)
    with db.connection() as conn:
        inserir_change(
            conn,
            "incidents",
            {
                "sys_id": "INC-1",
                "number": "INC-1",
                "opened_at": inicio,
                "priority": "P1",
                "state": "closed",
                "business_service": "playback",
                "short_description": "playback degradado",
            },
            pk={"sys_id": "INC-1"},
        )
        inserir_change(
            conn,
            "incident_label",
            {
                "id": "LBL-1",
                "tier": 1,
                "kind": "detector-derived",
                "ts_start": inicio,
                "ts_end": inicio + 900_000,
                "severity": "high",
                "services": "playback",
                "description": "rotulo derivado do detector",
            },
            pk={"id": "LBL-1"},
        )
        conn.execute("SELECT bronze.merge_todas()")
    # O gabarito CHEGOU na Bronze -- sem isso o assert seguinte passaria por
    # engano, provando apenas que o dado nunca foi ingerido.
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.incidents")["n"] == 1
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.incident_label")["n"] == 1

    assert etl.executar_bronze_silver(db, batch_size=1000)["status"] == "sucesso"

    # Nenhuma versao de fato veio das tabelas de gabarito.
    fontes = {
        row["source"]
        for row in db.fetch_all(
            "SELECT DISTINCT source FROM silver.analysis_fact_version"
        )
    }
    assert fontes == {"prometheus", "npaw_player"}
    assert not any("incident" in fonte or "label" in fonte for fonte in fontes)

    catalog = Catalog("test")
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, "test")
    captured = claim_and_capture(
        db, worker_id="worker-1", manifest_hash=catalog.manifest_hash
    )
    assert captured is not None
    assert all(fact.source in {"prometheus", "npaw_player"} for fact in captured.facts)
