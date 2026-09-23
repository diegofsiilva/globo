"""Servico de processamento -- ETL, detector, canario e hipoteses.

Ate a publicacao "Watermarks e workers de transicao de camada" (20/08/2026)
virar codigo, este container so provava que a infraestrutura (rede, security
group, senha, GRANT) estava correta. A partir desta versao ele tambem RODA o
ETL: dois lacos independentes, cada um dono do seu watermark
(`etl.watermark_bronze_silver`, `etl.watermark_silver_gold`), cada um na sua
cadencia -- exatamente o desenho de "dois workers separados" da publicacao,
so que como duas threads dentro do MESMO container em vez de dois servicos
ECS. A escolha e deliberada: a task definition, o log group, o alarme de
`RunningTaskCount` e a `DATABASE_URL` deste servico ja estavam provisionados
para o proposito de hospedar processamento (ver `infra/ecs_processing.tf`) --
criar dois servicos novos so para separar cadencia teria custado um ciclo de
`terraform apply` que o problema em si nao pede. Threads bastam porque cada
ciclo e uma UNICA chamada SQL (`etl.executar_bronze_silver` /
`etl.executar_silver_gold`): a atomicidade mora no banco, nao em memoria
compartilhada entre elas.

Uso:
    python -m argus_processing
"""

from __future__ import annotations

import logging
import os
import socket
import sys
import threading

from argus_common import Database, Heartbeat, Metrics, ShutdownSignal, configure_logging

from argus_processing import etl
from argus_processing.catalog import Catalog
from argus_processing.pipeline import analyze_once

log = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    """Le uma variavel de ambiente como inteiro.

    Args:
        name (str): Nome da variavel.
        default (int): Valor padrao.

    Returns:
        int: Valor lido, ou o padrao.
    """
    raw = os.getenv(name)
    return int(raw) if raw and raw.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    """Le uma variavel de ambiente booleana.

    Aceita as grafias usuais em vez de exigir uma so: o mesmo valor e escrito no
    Terraform, no `.env` e a mao no `docker run`, e cada um tem o seu costume.
    Qualquer outra coisa e falso -- inclusive `"false"`, que uma checagem por
    string nao vazia leria como verdadeiro.

    Args:
        name (str): Nome da variavel.
        default (bool): Valor quando a variavel nao esta definida.

    Returns:
        bool: O valor interpretado.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _drenar_bronze_silver(
    db: Database, metrics: Metrics, batch_size: int, shutdown: ShutdownSignal
) -> None:
    """Chama o ciclo bronze->silver em loop ate esvaziar o backlog.

    Args:
        db (Database): Pool de conexao.
        metrics (Metrics): Acumulador deste worker.
        batch_size (int): Teto de entradas do log por chamada.
        shutdown (ShutdownSignal): Permite interromper o dreno em SIGTERM, em
            vez de terminar o backlog inteiro antes de poder sair.
    """
    while shutdown.running:
        row = etl.executar_bronze_silver(db, batch_size)
        status = row["status"]
        if status == "sucesso":
            metrics.count("EtlBronzeSilverCiclos")
            metrics.count("EtlBronzeSilverLinhas", row["linhas"])
            log.info(
                "etl bronze->silver",
                extra={
                    "de_lsn": row["de_lsn"],
                    "ate_lsn": row["ate_lsn"],
                    "linhas": row["linhas"],
                },
            )
            continue  # pode haver mais backlog -- tenta de novo, sem esperar
        if status == "falha":
            metrics.count("EtlBronzeSilverFalha")
            log.error("etl bronze->silver falhou", extra={"erro": row["erro"]})
        return  # 'sem_pendencia' ou 'falha': nada mais a fazer neste tick


def _drenar_silver_gold(
    db: Database, metrics: Metrics, janela_max_segundos: int, shutdown: ShutdownSignal
) -> None:
    """Chama o ciclo silver->gold em loop ate alcancar o presente virtual.

    O alvo (`sim.now()`) e lido UMA VEZ, no inicio do dreno, e nao a cada
    chamada. `sim.now()` anda sozinho em tempo real (speed > 0), entao
    `ate_ts < sim.now()` reavaliado a cada iteracao NUNCA fica falso -- vira
    loop ocupado, sem sleep, martelando o banco. Congelar o alvo faz o dreno
    convergir num numero finito de chamadas (o backlog ate onde o relogio
    estava quando o dreno comecou) e devolver o controle ao chamador, que so
    volta a tentar depois de `intervalo_segundos`.

    Args:
        db (Database): Pool de conexao.
        metrics (Metrics): Acumulador deste worker.
        janela_max_segundos (int): Teto de tempo virtual absorvido por chamada.
        shutdown (ShutdownSignal): Permite interromper o dreno em SIGTERM.
    """
    alvo = db.sim_now()
    while shutdown.running:
        row = etl.executar_silver_gold(db, janela_max_segundos)
        status = row["status"]
        if status == "sucesso":
            metrics.count("EtlSilverGoldCiclos")
            metrics.count("EtlSilverGoldLinhas", row["linhas"])
            log.info(
                "etl silver->gold",
                extra={
                    "de_ts": str(row["de_ts"]),
                    "ate_ts": str(row["ate_ts"]),
                    "linhas": row["linhas"],
                },
            )
            if row["ate_ts"] < alvo:
                continue  # ainda ha backlog ate o alvo congelado no inicio
            return  # alcancou o alvo -- o resto e so o relogio andando
        if status == "falha":
            metrics.count("EtlSilverGoldFalha")
            log.error("etl silver->gold falhou", extra={"erro": row["erro"]})
        return


def _laco_bronze_silver(
    db: Database,
    shutdown: ShutdownSignal,
    metrics: Metrics,
    intervalo_segundos: int,
    batch_size: int,
) -> None:
    """Thread do worker bronze->silver: drena, dorme, repete.

    Args:
        db (Database): Pool de conexao (compartilhado com a thread irma; o
            pool do psycopg_pool ja e thread-safe).
        shutdown (ShutdownSignal): Compartilhado com o resto do processo.
        metrics (Metrics): Acumulador proprio desta thread -- cada thread tem
            o seu para o `flush()` de uma nao interromper o acumulo da outra.
        intervalo_segundos (int): Cadencia entre tentativas de dreno.
        batch_size (int): Repassado a cada chamada do ciclo.
    """
    log.info(
        "worker bronze->silver iniciado",
        extra={"intervalo_s": intervalo_segundos, "batch_size": batch_size},
    )
    while shutdown.running:
        try:
            _drenar_bronze_silver(db, metrics, batch_size, shutdown)
        except Exception:
            metrics.count("EtlBronzeSilverErroInesperado")
            log.exception("worker bronze->silver: erro inesperado no ciclo")
        metrics.flush()
        shutdown.sleep(intervalo_segundos)
    log.info("worker bronze->silver encerrado")


def _laco_silver_gold(
    db: Database,
    shutdown: ShutdownSignal,
    metrics: Metrics,
    intervalo_segundos: int,
    janela_max_segundos: int,
) -> None:
    """Thread do worker silver->gold: drena, dorme, repete.

    Args:
        db (Database): Pool de conexao, compartilhado com a thread irma.
        shutdown (ShutdownSignal): Compartilhado com o resto do processo.
        metrics (Metrics): Acumulador proprio desta thread.
        intervalo_segundos (int): Cadencia entre tentativas de dreno.
        janela_max_segundos (int): Repassado a cada chamada do ciclo.
    """
    log.info(
        "worker silver->gold iniciado",
        extra={"intervalo_s": intervalo_segundos, "janela_max_s": janela_max_segundos},
    )
    while shutdown.running:
        try:
            _drenar_silver_gold(db, metrics, janela_max_segundos, shutdown)
        except Exception:
            metrics.count("EtlSilverGoldErroInesperado")
            log.exception("worker silver->gold: erro inesperado no ciclo")
        metrics.flush()
        shutdown.sleep(intervalo_segundos)
    log.info("worker silver->gold encerrado")


def _laco_analise(
    db: Database,
    shutdown: ShutdownSignal,
    metrics: Metrics,
    catalog: Catalog,
    worker_id: str,
    intervalo_segundos: int,
    lease_segundos: int,
    heartbeat_segundos: int,
    max_input_rows: int,
    max_candidates: int,
    max_candidates_family: int,
    max_generated: int,
    code_version: str,
) -> None:
    """Drena checkpoints sequencialmente; dorme apenas quando nao ha trabalho."""
    log.info(
        "worker de analise iniciado",
        extra={"manifest_hash": catalog.manifest_hash, "worker_id": worker_id},
    )
    while shutdown.running:
        worked = False
        try:
            worked = analyze_once(
                db,
                metrics,
                catalog,
                worker_id=worker_id,
                code_version=code_version,
                lease_seconds=lease_segundos,
                heartbeat_seconds=heartbeat_segundos,
                max_input_rows=max_input_rows,
                max_candidates=max_candidates,
                max_candidates_per_family=max_candidates_family,
                max_generated=max_generated,
            )
        except Exception:
            metrics.count("AnalysisUnexpectedError")
            log.exception("worker de analise: erro no ciclo")
        metrics.flush()
        if not worked:
            shutdown.sleep(intervalo_segundos)
    log.info("worker de analise encerrado")


def main() -> int:
    """Ponto de entrada.

    Returns:
        int: 0 em sucesso, 1 em falha.
    """
    service_name = os.getenv("SERVICE_NAME", "argus-processing")
    log_ = configure_logging(os.getenv("LOG_LEVEL", "INFO").upper(), service_name)
    tick = _env_int("TICK_SECONDS", 30)

    etl_bs_intervalo = _env_int("ETL_BRONZE_SILVER_INTERVAL_SECONDS", 60)
    etl_bs_batch = _env_int("ETL_BRONZE_SILVER_BATCH_SIZE", 5000)
    etl_sg_intervalo = _env_int("ETL_SILVER_GOLD_INTERVAL_SECONDS", 900)
    # PRECISA ser maior que etl.watermark_silver_gold.margem_seguranca (2h por
    # default -- ver 015_etl_incremental.sql), senao o watermark nao avanca e
    # etl.executar_silver_gold levanta erro de configuracao a cada chamada.
    # 4h da 2h de progresso real por ciclo com backlog, sem exagerar no lote.
    etl_sg_janela = _env_int("ETL_SILVER_GOLD_JANELA_MAX_SECONDS", 14400)

    analysis_enabled = _env_bool("ANALYSIS_ENABLED", True)
    analysis_interval = _env_int("ANALYSIS_POLL_SECONDS", 30)
    analysis_lease = _env_int("ANALYSIS_LEASE_SECONDS", 120)
    analysis_heartbeat = _env_int("ANALYSIS_HEARTBEAT_SECONDS", 30)
    analysis_max_input = _env_int("ANALYSIS_MAX_INPUT_ROWS", 250_000)
    analysis_max_candidates = _env_int("ANALYSIS_MAX_CANDIDATES", 10_000)
    analysis_max_family = _env_int("ANALYSIS_MAX_CANDIDATES_PER_FAMILY", 2_000)
    analysis_max_generated = _env_int("ANALYSIS_MAX_GENERATED", 500)

    metrics_namespace = os.getenv("METRICS_NAMESPACE", "Argus/Ingestion")
    metrics = Metrics(metrics_namespace, service_name)
    heartbeat = Heartbeat(os.getenv("HEARTBEAT_PATH", "/tmp/argus-heartbeat"))
    shutdown = ShutdownSignal()

    db = None
    threads: list[threading.Thread] = []
    try:
        # ETLs, analise e heartbeat de lease precisam progredir sem disputar a
        # ultima conexao do pool.
        db = Database.from_env(min_size=1, max_size=8, application_name=service_name)
        log_.info("processamento iniciado", extra={"tick_seconds": tick})

        threads = [
            threading.Thread(
                target=_laco_bronze_silver,
                args=(
                    db,
                    shutdown,
                    Metrics(metrics_namespace, f"{service_name}-bronze-silver"),
                    etl_bs_intervalo,
                    etl_bs_batch,
                ),
                name="etl-bronze-silver",
            ),
            threading.Thread(
                target=_laco_silver_gold,
                args=(
                    db,
                    shutdown,
                    Metrics(metrics_namespace, f"{service_name}-silver-gold"),
                    etl_sg_intervalo,
                    etl_sg_janela,
                ),
                name="etl-silver-gold",
            ),
        ]
        if analysis_enabled:
            code_version = os.getenv("IMAGE_TAG", "local")
            catalog = Catalog(code_version)
            threads.append(
                threading.Thread(
                    target=_laco_analise,
                    args=(
                        db,
                        shutdown,
                        Metrics(metrics_namespace, f"{service_name}-analysis"),
                        catalog,
                        f"{socket.gethostname()}:{os.getpid()}",
                        analysis_interval,
                        analysis_lease,
                        analysis_heartbeat,
                        analysis_max_input,
                        analysis_max_candidates,
                        analysis_max_family,
                        analysis_max_generated,
                        code_version,
                    ),
                    name="analysis",
                )
            )
        for t in threads:
            t.start()

        while shutdown.running:
            heartbeat.touch()

            if db.healthy():
                metrics.count("ProcessingHeartbeat")
                # O relogio virtual e o que os dois workers de ETL usam como
                # "agora". Publicar aqui deixa visivel, no log, que o simulador
                # esta andando -- um relogio parado explica sozinho por que a
                # gold parou de avancar.
                metrics.count("ClockAlive")
                log_.info("vivo", extra={"sim_now": db.sim_now().isoformat()})
            else:
                metrics.count("ProcessingDbUnreachable")
                log_.warning("banco inalcancavel neste ciclo")

            metrics.flush()
            shutdown.sleep(tick)

        log_.info("processamento encerrado")
    except Exception:
        log_.exception("processamento abortou")
        return 1
    finally:
        for t in threads:
            t.join(timeout=30)
        if db is not None:
            db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
