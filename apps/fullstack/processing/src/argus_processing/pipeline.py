"""Orquestracao de um ciclo completo de analise."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any

from argus_common import Database, Metrics

from argus_processing.analysis_repository import (
    CapturedWork,
    CaptureLimitExceeded,
    claim_and_capture,
    load_baselines,
    load_historical_anomalies,
    persist_result,
    register_manifest,
)
from argus_processing.catalog import Catalog
from argus_processing.detector import detect
from argus_processing.domain import AnalysisResult
from argus_processing.orchestration import (
    FencingRejected,
    falhar_trabalho,
    iniciar_trabalho,
    renovar_lease,
)
from argus_processing.quality import evaluate_quality
from argus_processing.rules import build_candidates, evaluate_candidates

log = logging.getLogger(__name__)


def _stream_key(db: Database, run_id: int) -> str:
    """Le a `stream_key` de um run.

    Args:
        db (Database): Conexao com o banco.
        run_id (int): Execucao consultada.

    Returns:
        str: A chave do fluxo, que junto com o `manifest_hash` identifica o
            cursor de progresso.

    Raises:
        RuntimeError: Se o run nao existir mais -- sinal de que outro processo
            o removeu, e continuar gravaria resultado sob um cursor alheio.
    """
    row = db.fetch_one("SELECT stream_key FROM detect.run WHERE run_id = %s", (run_id,))
    if row is None:
        raise RuntimeError(f"run {run_id} desapareceu")
    return str(row["stream_key"])


@contextmanager
def lease_heartbeat(
    db: Database,
    captured: CapturedWork,
    *,
    interval_seconds: int,
    lease_seconds: int,
):
    """Renova o lease do claim numa thread enquanto o bloco roda.

    Um ciclo de analise pode passar do tempo do lease. Sem renovacao, outro
    worker consideraria este abandonado e assumiria o trabalho -- dois runs
    concorrentes sobre o mesmo cursor publicariam hipoteses inconsistentes.

    O evento devolvido e a via de mao contraria: quando a renovacao FALHA, este
    processo ja perdeu a posse e precisa parar antes de gravar. Descobrir isso
    no commit seria tarde.

    Args:
        db (Database): Conexao com o banco.
        captured (CapturedWork): Trabalho capturado, com o claim a renovar.
        interval_seconds (int): Intervalo entre renovacoes.
        lease_seconds (int): Duracao concedida em cada renovacao.

    Yields:
        threading.Event: Sinalizado quando o lease e perdido.
    """
    stop = threading.Event()
    lost = threading.Event()

    def loop() -> None:
        """Renova ate o bloco terminar ou a posse ser perdida."""
        while not stop.wait(interval_seconds):
            if not renovar_lease(db, captured.claim, lease_seconds=lease_seconds):
                lost.set()
                return

    thread = threading.Thread(target=loop, name=f"analysis-lease-{captured.claim.run_id}")
    thread.start()
    try:
        yield lost
    finally:
        stop.set()
        thread.join(timeout=max(1, interval_seconds))


def run_captured(
    db: Database,
    captured: CapturedWork,
    catalog: Catalog,
    *,
    heartbeat_seconds: int = 30,
    lease_seconds: int = 120,
    max_candidates: int = 10_000,
    max_candidates_per_family: int = 2_000,
    max_generated: int = 500,
) -> AnalysisResult:
    """Executa o ciclo de analise sobre um trabalho ja capturado.

    Canario -> detector -> regras -> score -> gravacao, tudo sob o lease. A
    captura acontece ANTES (em `claim_and_capture`), em `REPEATABLE READ`: e o
    que garante que o ciclo inteiro enxergue o mesmo instantaneo do banco,
    mesmo com o ETL escrevendo em paralelo.

    Args:
        db (Database): Conexao com o banco.
        captured (CapturedWork): Fatos, janela e claim.
        catalog (Catalog): Catalogos e parametros.
        heartbeat_seconds (int): Intervalo de renovacao do lease.
        lease_seconds (int): Duracao concedida em cada renovacao.
        max_candidates (int): Teto de candidatos avaliados.
        max_candidates_per_family (int): Teto por familia.
        max_generated (int): Teto de hipoteses publicadas.

    Returns:
        AnalysisResult: Anomalias, qualidade, hipoteses e os contadores de corte.

    Raises:
        RuntimeError: Se a posse for perdida antes de iniciar ou durante o ciclo.
    """
    if not iniciar_trabalho(db, captured.claim):
        raise RuntimeError(f"run {captured.claim.run_id} perdeu a posse antes de iniciar")
    started = time.monotonic()
    with lease_heartbeat(
        db, captured, interval_seconds=heartbeat_seconds, lease_seconds=lease_seconds
    ) as lost:
        quality = evaluate_quality(
            captured.facts,
            catalog,
            window_start=captured.window_start,
            window_end=captured.window_end,
            simulator_end=captured.simulator_end,
        )
        baselines = load_baselines(
            db, captured.claim.manifest_hash, _stream_key(db, captured.claim.run_id)
        )
        anomalies, baseline_updates = detect(captured.facts, baselines, catalog)
        # Findings anteriores cujos fatos voltaram na captura (fonte causalmente
        # atrasada, como NPAW) entram como anomalia indexavel sem serem
        # reinseridos: eles ja tem `persisted_id`. A lista concatenada e a que
        # `anomaly_indexes` enderecam, entao precisa ser a mesma nas duas etapas.
        finding_anomalies = anomalies + load_historical_anomalies(db, captured)
        candidates = build_candidates(finding_anomalies, captured.facts, quality, catalog)
        hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
            candidates,
            finding_anomalies,
            quality,
            catalog,
            max_total=max_candidates,
            max_per_family=max_candidates_per_family,
            max_generated=max_generated,
        )
        result = AnalysisResult(
            anomalies=anomalies,
            finding_anomalies=finding_anomalies,
            baseline_updates=baseline_updates,
            quality=quality,
            hypotheses=hypotheses,
            candidates_prefiltered=prefiltered,
            candidates_evaluated=evaluated,
            candidates_truncated=truncated,
        )
        if lost.is_set():
            raise RuntimeError(f"run {captured.claim.run_id} perdeu o lease")
        persist_result(
            db,
            captured,
            result,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        return result


def analyze_once(
    db: Database,
    metrics: Metrics,
    catalog: Catalog,
    *,
    worker_id: str,
    code_version: str,
    lease_seconds: int = 120,
    heartbeat_seconds: int = 30,
    max_input_rows: int = 250_000,
    max_candidates: int = 10_000,
    max_candidates_per_family: int = 2_000,
    max_generated: int = 500,
) -> bool:
    """Roda UM ciclo completo: reivindica trabalho, analisa e grava.

    Args:
        db (Database): Conexao com o banco.
        metrics (Metrics): Publicador de metricas no CloudWatch.
        catalog (Catalog): Catalogos e parametros.
        worker_id (str): Identifica quem detem o claim, para o takeover.
        code_version (str): Entra no manifesto; ver `Catalog.__init__`.
        lease_seconds (int): Duracao do lease.
        heartbeat_seconds (int): Intervalo de renovacao.
        max_input_rows (int): Teto de linhas capturadas por ciclo.
        max_candidates (int): Teto de candidatos avaliados.
        max_candidates_per_family (int): Teto por familia.
        max_generated (int): Teto de hipoteses publicadas.

    Returns:
        bool: `True` se havia trabalho e ele foi concluido; `False` quando nao
            havia nada a fazer -- o laco principal usa isso para decidir entre
            emendar outro ciclo e dormir.
    """
    register_manifest(db, catalog.manifest_hash, catalog.manifest_payload, code_version)
    try:
        captured = claim_and_capture(
            db,
            worker_id=worker_id,
            manifest_hash=catalog.manifest_hash,
            lease_seconds=lease_seconds,
            max_input_rows=max_input_rows,
        )
    except CaptureLimitExceeded:
        metrics.count("AnalysisInputLimitExceeded")
        raise
    if captured is None:
        return False

    metrics.count("AnalysisRunsStarted")
    metrics.count("AnalysisInputRows", len(captured.facts))
    if captured.claim.attempt > 1:
        metrics.count("AnalysisTakeovers")
    started = time.monotonic()
    try:
        result = run_captured(
            db,
            captured,
            catalog,
            heartbeat_seconds=heartbeat_seconds,
            lease_seconds=lease_seconds,
            max_candidates=max_candidates,
            max_candidates_per_family=max_candidates_per_family,
            max_generated=max_generated,
        )
    except Exception as error:
        falhar_trabalho(db, captured.claim, str(error)[:4000])
        metrics.count("AnalysisRunsFailed")
        if isinstance(error, FencingRejected):
            metrics.count("AnalysisFencingRejected")
        raise

    metrics.count("AnalysisRunsCompleted")
    metrics.duration_ms("AnalysisDurationMs", (time.monotonic() - started) * 1000)
    metrics.count("AnalysisAnomalies", len(result.anomalies))
    metrics.count(
        "AnalysisHypothesesGenerated",
        sum(h.evaluation_status == "generated" for h in result.hypotheses),
    )
    metrics.count("AnalysisCandidatesTruncated", result.candidates_truncated)
    metrics.count(
        "AnalysisHypothesesInsufficient",
        sum(h.evaluation_status == "insufficient_evidence" for h in result.hypotheses),
    )
    metrics.count(
        "AnalysisHypothesesDiscarded",
        sum(h.evaluation_status == "discarded" for h in result.hypotheses),
    )
    operational = db.fetch_one(
        """
        SELECT count(*) FILTER (
                 WHERE gc.checkpoint_id > %s
                   AND gc.sim_run_id IS NOT DISTINCT FROM r.sim_run_id
               ) AS backlog,
               greatest(0, extract(epoch FROM (sim.now() - r.sim_now))) AS lag_seconds
          FROM detect.run r
          CROSS JOIN etl.gold_checkpoint gc
         WHERE r.run_id = %s
         GROUP BY r.sim_now
        """,
        (captured.claim.checkpoint_id, captured.claim.run_id),
    )
    if operational:
        metrics.count("AnalysisBacklogCheckpoints", operational["backlog"])
        metrics.count("AnalysisLagSimSeconds", float(operational["lag_seconds"]))
    log.info(
        "analise concluida",
        extra={
            "run_id": captured.claim.run_id,
            "checkpoint_id": captured.claim.checkpoint_id,
            "manifest_hash": captured.claim.manifest_hash,
            "fencing_token": captured.claim.fencing_token,
            "input_rows": len(captured.facts),
            "anomalies": len(result.anomalies),
            "hypotheses": len(result.hypotheses),
        },
    )
    return True


def manifest_summary(catalog: Catalog) -> dict[str, Any]:
    """Manifesto do motor com o seu hash, para inspecao pela CLI.

    Args:
        catalog (Catalog): Catalogo carregado.

    Returns:
        dict[str, Any]: O payload do manifesto mais o `manifest_hash`. Serve
            para comparar a configuracao de duas execucoes: hashes diferentes
            significam resultados nao comparaveis.
    """
    return {"manifest_hash": catalog.manifest_hash, **catalog.manifest_payload}
