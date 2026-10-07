"""Captura consistente e persistencia transacional da analise."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from argus_common import Database
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from argus_processing.domain import AnalysisResult, Anomaly, Baseline, Fact
from argus_processing.orchestration import (
    CLAIM_ADVISORY_LOCK_KEY,
    WorkClaim,
    commit_protegido,
)


class CaptureLimitExceeded(RuntimeError):
    """A unidade excedeu o limite e foi persistida como falha."""


class InputDigestMismatch(RuntimeError):
    """Um retry reconstruiu entrada diferente para o mesmo checkpoint."""


@dataclass(frozen=True, slots=True)
class CapturedWork:
    """Um instantaneo de trabalho: o claim mais os fatos ja lidos.

    A captura acontece em `REPEATABLE READ` e ANTES da analise. E o que faz o
    ciclo inteiro enxergar o mesmo estado do banco mesmo com o ETL escrevendo
    em paralelo -- sem isso, o detector veria uma janela e as regras veriam
    outra, e a hipotese citaria evidencia que a anomalia nao considerou.

    `simulator_end` marca ate onde o simulador chegou. Sem ele, o canario
    avaliaria uma janela alem do que foi emitido e reprovaria TODA fonte por
    incompletude.
    """

    claim: WorkClaim
    facts: tuple[Fact, ...]
    window_start: dt.datetime
    window_end: dt.datetime
    simulator_end: dt.datetime | None


def _claim(row: dict[str, Any]) -> WorkClaim:
    """Converte uma linha de `detect.run` no claim tipado.

    Args:
        row (dict[str, Any]): Linha do cursor.

    Returns:
        WorkClaim: A posse do trabalho, com lease e `fencing_token`.
    """
    return WorkClaim(
        run_id=row["run_id"],
        checkpoint_id=row["checkpoint_id"],
        manifest_hash=row["manifest_hash"],
        sim_now=row["sim_now"],
        claimed_by=row["claimed_by"],
        lease_expires_at=row["lease_expires_at"],
        heartbeat_at=row["heartbeat_at"],
        fencing_token=row["fencing_token"],
        attempt=row["attempt"],
        retry_of=row["retry_of"],
        input_lsn=row["input_lsn"],
        status=row["status"],
    )


def _fact(row: dict[str, Any]) -> Fact:
    """Converte uma linha de `silver.analysis_fact_version` num `Fact`.

    Args:
        row (dict[str, Any]): Linha do cursor.

    Returns:
        Fact: O fato imutavel usado pelo detector e pelas regras.
    """
    return Fact(
        fact_key=row["fact_key"],
        version_lsn=row["version_lsn"],
        role=row["role"],
        kind=row["kind"],
        event_start=row["event_start"],
        event_end=row["event_end"],
        available_at=row["available_at"],
        source=row["source"],
        entity=row["entity"],
        metric=row["metric"],
        dimension_type=row["dimension_type"],
        dimension_value=row["dimension_value"],
        value=row["value"],
        sample_size=row["sample_size"],
        attributes=dict(row["attributes"] or {}),
    )


def register_manifest(
    db: Database, manifest_hash: str, payload: dict[str, Any], code_version: str
) -> None:
    """Grava o manifesto do motor, se ainda nao existir.

    Recalcula o hash a partir do payload e recusa quando diverge do informado.
    A checagem parece redundante -- o mesmo objeto acabou de produzir os dois --
    mas ela e o que impede gravar um par (hash, configuracao) inconsistente, que
    tornaria todo resultado ligado a esse hash irreprodutivel.

    Args:
        db (Database): Conexao com o banco.
        manifest_hash (str): Hash calculado pelo `Catalog`.
        payload (dict[str, Any]): Catalogos e parametros.
        code_version (str): Versao do codigo.

    Returns:
        None: A função persiste o manifesto sem produzir valor de retorno.

    Raises:
        RuntimeError: Se o hash recalculado nao bater com o informado.
    """
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    calculated_hash = hashlib.sha256(canonical.encode()).hexdigest()
    if calculated_hash != manifest_hash:
        raise ValueError("manifest_hash does not match the canonical payload")
    if payload.get("code_version") != code_version:
        raise ValueError("code_version does not match the manifest payload")

    with db.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO detect.manifest (manifest_hash, payload, code_version)
            VALUES (%s, %s, %s)
            ON CONFLICT (manifest_hash) DO NOTHING
            RETURNING manifest_hash
            """,
            (manifest_hash, Jsonb(payload), code_version),
        ).fetchone()
        if row is None:
            existing = conn.execute(
                """
                SELECT payload, code_version
                  FROM detect.manifest
                 WHERE manifest_hash = %s
                """,
                (manifest_hash,),
            ).fetchone()
            if existing is None or existing[0] != payload or existing[1] != code_version:
                raise RuntimeError(
                    "manifest hash collision or immutable manifest mismatch"
                )


def claim_and_capture(
    db: Database,
    *,
    worker_id: str,
    manifest_hash: str,
    lease_seconds: int = 120,
    max_input_rows: int = 250_000,
    context_minutes: int = 60,
) -> CapturedWork | None:
    """Reivindica trabalho e captura fatos no mesmo snapshot repetível.

    Cria ou bloqueia o cursor do manifesto e do fluxo, resolve claims ativos
    e escolhe o próximo checkpoint elegível. Em uma única transação
    ``REPEATABLE READ`` grava a identidade das versões de fatos que alimentam
    o run. Se outra réplica já detém o claim, se não há checkpoint novo ou se
    os limites de captura são excedidos, não inicia um ciclo concorrente.

    Args:
        db: Pool de conexões do Argus.
        worker_id: Identificador desta réplica ou tentativa.
        manifest_hash: Identidade do catálogo e dos parâmetros do detector.
        lease_seconds: Duração inicial do claim em tempo real.
        max_input_rows: Limite de fatos capturados para um run.
        context_minutes: Janela de contexto anterior ao checkpoint.

    Returns:
        Captura imutável com fatos, janela, checkpoint e claim, ou ``None``
        quando não há trabalho que esta réplica possa reivindicar.

    Raises:
        CaptureLimitExceeded: Se a captura exceder o limite de linhas.
        InputDigestMismatch: Se os fatos capturados não corresponderem ao
            resumo persistido para a entrada do run.
    """
    exceeded: str | None = None
    claim_row: dict[str, Any] | None = None
    window_start: dt.datetime | None = None
    window_end: dt.datetime | None = None
    simulator_end: dt.datetime | None = None

    with db.connection() as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT pg_try_advisory_xact_lock(%s) AS acquired",
                (CLAIM_ADVISORY_LOCK_KEY,),
            )
            if not cur.fetchone()["acquired"]:
                return None

            cur.execute(
                """
                SELECT sim_run_id
                  FROM etl.gold_checkpoint
                 ORDER BY checkpoint_id DESC
                 LIMIT 1
                """
            )
            latest = cur.fetchone()
            if latest is None:
                return None
            sim_run_id = latest["sim_run_id"]
            stream_key = f"sim:{sim_run_id}" if sim_run_id is not None else "live"

            cur.execute(
                """
                INSERT INTO detect.analysis_cursor (manifest_hash, stream_key, sim_run_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (manifest_hash, stream_key) DO NOTHING
                """,
                (manifest_hash, stream_key, sim_run_id),
            )
            cur.execute(
                """
                SELECT * FROM detect.analysis_cursor
                 WHERE manifest_hash = %s AND stream_key = %s
                 FOR UPDATE
                """,
                (manifest_hash, stream_key),
            )
            cursor = cur.fetchone()

            previous_run = None
            if cursor["active_run_id"] is not None:
                cur.execute(
                    """
                    SELECT r.*, clock_timestamp() AS now_real
                      FROM detect.run r
                     WHERE r.run_id = %s
                     FOR UPDATE
                    """,
                    (cursor["active_run_id"],),
                )
                active = cur.fetchone()
                if active and active["status"] in {"claimed", "running", "committing"}:
                    if active["lease_expires_at"] > active["now_real"]:
                        return None
                    cur.execute(
                        """
                        UPDATE detect.run
                           SET status = 'abandoned', finished_at = clock_timestamp(),
                               error_message = COALESCE(error_message, 'lease expirado')
                         WHERE run_id = %s
                        """,
                        (active["run_id"],),
                    )
                if active and active["status"] != "completed":
                    previous_run = active

            if previous_run is not None:
                cur.execute(
                    "SELECT * FROM etl.gold_checkpoint WHERE checkpoint_id = %s",
                    (previous_run["checkpoint_id"],),
                )
                checkpoint = cur.fetchone()
            else:
                cur.execute(
                    """
                    SELECT * FROM etl.gold_checkpoint
                     WHERE checkpoint_id > COALESCE(%s, 0)
                       AND sim_run_id IS NOT DISTINCT FROM %s
                     ORDER BY checkpoint_id
                     LIMIT 1
                    """,
                    (cursor["last_completed_checkpoint_id"], sim_run_id),
                )
                checkpoint = cur.fetchone()
            if checkpoint is None:
                return None

            cur.execute("SELECT clock_timestamp() AS now_real")
            now_real = cur.fetchone()["now_real"]
            retry_of = previous_run["run_id"] if previous_run else None
            attempt = previous_run["attempt"] + 1 if previous_run else 1
            cur.execute("SELECT nextval('detect.fencing_token_seq') AS token")
            token = cur.fetchone()["token"]
            lease_expires = now_real + dt.timedelta(seconds=lease_seconds)
            if cursor["last_ready_through"] is not None:
                window_start = cursor["last_ready_through"]
            elif sim_run_id is not None:
                cur.execute("SELECT t0 FROM sim.run WHERE run_id = %s", (sim_run_id,))
                sim_start = cur.fetchone()
                window_start = min(
                    sim_start["t0"] if sim_start else checkpoint["ready_through"],
                    checkpoint["ready_through"],
                )
            else:
                window_start = checkpoint["ready_through"] - dt.timedelta(
                    minutes=context_minutes
                )
            window_end = checkpoint["ready_through"]

            cur.execute(
                """
                INSERT INTO detect.run (
                  sim_run_id, detector, params, checkpoint_id, previous_checkpoint_id,
                  manifest_hash, sim_now, status, claimed_by, lease_expires_at,
                  heartbeat_at, fencing_token, attempt, retry_of, input_lsn, stream_key
                ) VALUES (
                  %s, 'argus-rules', '{}'::jsonb, %s, %s,
                  %s, %s, 'claimed', %s, %s,
                  %s, %s, %s, %s, %s, %s
                )
                RETURNING *
                """,
                (
                    sim_run_id,
                    checkpoint["checkpoint_id"],
                    cursor["last_completed_checkpoint_id"],
                    manifest_hash,
                    checkpoint["ready_through"],
                    worker_id,
                    lease_expires,
                    now_real,
                    token,
                    attempt,
                    retry_of,
                    checkpoint["source_lsn"],
                    stream_key,
                ),
            )
            claim_row = cur.fetchone()

            if previous_run is None:
                cur.execute(
                    """
                    INSERT INTO detect.work_claim (
                      checkpoint_id, manifest_hash, run_id, claimed_by,
                      lease_expires_at, heartbeat_at, fencing_token
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (checkpoint_id, manifest_hash) DO UPDATE
                      SET run_id = EXCLUDED.run_id,
                          claimed_by = EXCLUDED.claimed_by,
                          lease_expires_at = EXCLUDED.lease_expires_at,
                          heartbeat_at = EXCLUDED.heartbeat_at,
                          fencing_token = EXCLUDED.fencing_token,
                          updated_at = clock_timestamp()
                    """,
                    (
                        checkpoint["checkpoint_id"],
                        manifest_hash,
                        claim_row["run_id"],
                        worker_id,
                        lease_expires,
                        now_real,
                        token,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE detect.work_claim
                       SET run_id = %s, claimed_by = %s, lease_expires_at = %s,
                           heartbeat_at = %s, fencing_token = %s,
                           updated_at = clock_timestamp()
                     WHERE checkpoint_id = %s AND manifest_hash = %s
                    """,
                    (
                        claim_row["run_id"],
                        worker_id,
                        lease_expires,
                        now_real,
                        token,
                        checkpoint["checkpoint_id"],
                        manifest_hash,
                    ),
                )

            # A CTE escolhe a versao as-of do fato, identifica o delta do
            # checkpoint e inclui uma hora de contexto ao redor dele.
            selection = """
                WITH current_facts AS (
                  SELECT DISTINCT ON (f.fact_key) f.*
                    FROM silver.analysis_fact_version f
                   WHERE f.version_lsn <= %(input_lsn)s
                     AND f.available_at <= %(sim_now)s
                     AND f.event_start <= %(sim_now)s
                   ORDER BY f.fact_key, f.version_lsn DESC
                ), subjects AS (
                  SELECT * FROM current_facts
                   WHERE NOT is_deleted
                     AND (
                       version_lsn > %(previous_lsn)s
                       OR available_at > %(previous_ready)s
                     )
                ), quality_latest AS (
                  SELECT DISTINCT ON (f.source) f.*
                    FROM current_facts f
                   WHERE NOT f.is_deleted AND f.kind = 'metric'
                   ORDER BY f.source, f.available_at DESC, f.event_start DESC,
                            f.fact_key
                ), context_facts AS (
                  SELECT f.*
                    FROM current_facts f
                   WHERE NOT f.is_deleted
                     AND NOT EXISTS (
                       SELECT 1 FROM subjects s WHERE s.fact_key = f.fact_key
                     )
                     AND EXISTS (
                       SELECT 1 FROM subjects seed
                        WHERE f.event_start BETWEEN
                              seed.event_start - %(context)s::interval AND
                              seed.event_start + %(context)s::interval
                          AND (
                            f.entity = seed.entity OR f.kind = 'context'
                            OR f.dimension_value = seed.dimension_value
                          )
                     )
                ), selected AS (
                  SELECT s.*, 'subject'::text AS input_role
                    FROM subjects s
                   WHERE NOT s.is_deleted
                  UNION ALL
                  SELECT q.*, 'quality'::text
                    FROM quality_latest q
                   WHERE NOT EXISTS (
                     SELECT 1 FROM subjects s WHERE s.fact_key = q.fact_key
                   )
                  UNION ALL
                  SELECT c.*, 'context'::text
                    FROM context_facts c
                   WHERE NOT EXISTS (
                     SELECT 1 FROM quality_latest q WHERE q.fact_key = c.fact_key
                   )
                )
            """
            bind = {
                "input_lsn": checkpoint["source_lsn"],
                "sim_now": checkpoint["ready_through"],
                "previous_lsn": cursor["last_source_lsn"],
                "previous_ready": cursor["last_ready_through"]
                or dt.datetime.min.replace(tzinfo=dt.UTC),
                "context": f"{context_minutes} minutes",
            }
            cur.execute(selection + "SELECT count(*) AS n FROM selected", bind)
            input_rows = cur.fetchone()["n"]
            if input_rows > max_input_rows:
                exceeded = f"input_limit_exceeded:{input_rows}>{max_input_rows}"
                cur.execute(
                    """
                    UPDATE detect.run
                       SET status = 'failed', finished_at = clock_timestamp(),
                           error_message = %s, input_rows = %s
                     WHERE run_id = %s
                    """,
                    (exceeded, input_rows, claim_row["run_id"]),
                )
            else:
                cur.execute(
                    selection
                    + """
                    INSERT INTO detect.run_input_fact (
                      run_id, fact_key, version_lsn, role
                    )
                    SELECT %(run_id)s, fact_key, version_lsn, input_role FROM selected
                    """,
                    {**bind, "run_id": claim_row["run_id"]},
                )
                cur.execute(
                    """
                    SELECT COALESCE(sum(length(i.fact_key) + 16), 0) AS bytes,
                           encode(digest(COALESCE(string_agg(
                             i.fact_key || ':' || i.version_lsn || ':' || i.role,
                             ',' ORDER BY i.fact_key, i.version_lsn, i.role
                           ), ''), 'sha256'), 'hex') AS digest
                      FROM detect.run_input_fact i
                     WHERE i.run_id = %s
                    """,
                    (claim_row["run_id"],),
                )
                captured = cur.fetchone()
                cur.execute(
                    """
                    SELECT input_digest
                      FROM detect.run
                     WHERE checkpoint_id = %s AND manifest_hash = %s
                       AND run_id <> %s AND input_digest IS NOT NULL
                     ORDER BY attempt
                     LIMIT 1
                    """,
                    (
                        checkpoint["checkpoint_id"],
                        manifest_hash,
                        claim_row["run_id"],
                    ),
                )
                original = cur.fetchone()
                divergiu = (
                    original is not None
                    and original["input_digest"] != captured["digest"]
                )
                if divergiu:
                    exceeded = (
                        "input_digest_mismatch:"
                        f"{original['input_digest']}!={captured['digest']}"
                    )
                cur.execute(
                    """
                    UPDATE detect.run
                       SET input_digest = %s, input_rows = %s, input_bytes = %s,
                           status = CASE WHEN %s::text IS NULL
                                         THEN status ELSE 'failed' END,
                           finished_at = CASE WHEN %s::text IS NULL THEN finished_at
                                              ELSE clock_timestamp() END,
                           error_message = COALESCE(%s, error_message)
                     WHERE run_id = %s
                    """,
                    (
                        captured["digest"],
                        input_rows,
                        captured["bytes"],
                        exceeded,
                        exceeded,
                        exceeded,
                        claim_row["run_id"],
                    ),
                )
                claim_row["input_digest"] = captured["digest"]

            # Inclusive nos erros de integridade/limite o cursor aponta para a
            # tentativa encerrada. Assim o proximo claim reconhece o retry,
            # incrementa attempt e nunca pula o checkpoint problemático.
            cur.execute(
                """
                UPDATE detect.analysis_cursor
                   SET active_run_id = %s, updated_at = clock_timestamp()
                 WHERE manifest_hash = %s AND stream_key = %s
                """,
                (claim_row["run_id"], manifest_hash, stream_key),
            )

            if sim_run_id is not None:
                cur.execute("SELECT t1 FROM sim.run WHERE run_id = %s", (sim_run_id,))
                sim_row = cur.fetchone()
                simulator_end = sim_row["t1"] if sim_row else None

    if exceeded:
        if exceeded.startswith("input_digest_mismatch"):
            raise InputDigestMismatch(exceeded)
        raise CaptureLimitExceeded(exceeded)
    if claim_row is None or window_start is None or window_end is None:
        return None
    claim = _claim(claim_row)
    return CapturedWork(
        claim=claim,
        facts=load_run_input(db, claim.run_id),
        window_start=window_start,
        window_end=window_end,
        simulator_end=simulator_end,
    )


def load_run_input(db: Database, run_id: int) -> tuple[Fact, ...]:
    """Recarrega EXATAMENTE os fatos que alimentaram um run.

    Le de `detect.run_input_fact`, que registra a versao (`version_lsn`) de cada
    fato usado. E o que permite reexecutar um run e obter o mesmo resultado
    mesmo depois de a tabela corrente ter mudado -- reler "os fatos daquela
    janela" traria as versoes de agora, e a reproducao divergiria.

    Args:
        db (Database): Conexao com o banco.
        run_id (int): Execucao consultada.

    Returns:
        tuple[Fact, ...]: Os fatos na ordem canonica de leitura.
    """
    rows = db.fetch_all(
        """
        SELECT i.role, f.*
          FROM detect.run_input_fact i
          JOIN silver.analysis_fact_version f
            ON f.fact_key = i.fact_key AND f.version_lsn = i.version_lsn
         WHERE i.run_id = %s
         ORDER BY f.event_start, f.source, f.entity, f.metric, f.fact_key
        """,
        (run_id,),
    )
    return tuple(_fact(dict(row)) for row in rows)


def load_baselines(
    db: Database, manifest_hash: str, stream_key: str
) -> dict[tuple[str, str, str, int], Baseline]:
    """Carrega o estado do baseline circadiano de um fluxo.

    A chave inclui `hour_brt`: o baseline e POR HORA DO DIA, e nao uma media
    unica da serie. Sem essa separacao, o pico normal do horario nobre seria
    lido como anomalia toda noite, e a madrugada esconderia degradacao real.

    O `manifest_hash` faz parte da chave porque um baseline acumulado sob outra
    configuracao de detector nao e comparavel com o atual.

    Args:
        db (Database): Conexao com o banco.
        manifest_hash (str): Manifesto do motor.
        stream_key (str): Fluxo analisado.

    Returns:
        dict[tuple[str, str, str, int], Baseline]: Estado por
            (fonte, entidade, metrica, hora).
    """
    rows = db.fetch_all(
        """
        SELECT source, entity, metric, hour_brt, mean, variance, n, last_event_at
          FROM detect.baseline_state
         WHERE manifest_hash = %s AND stream_key = %s
        """,
        (manifest_hash, stream_key),
    )
    return {
        (row["source"], row["entity"], row["metric"], row["hour_brt"]): Baseline(
            row["mean"], row["variance"], row["n"], row["last_event_at"]
        )
        for row in rows
    }


def load_historical_anomalies(
    db: Database, captured: CapturedWork
) -> tuple[Anomaly, ...]:
    """Recupera findings anteriores cujos fatos fazem parte da captura atual.

    Isso permite que uma fonte causalmente atrasada (NPAW, por exemplo) revise
    uma hipótese do período original sem recalcular o passado com informação do
    futuro. O fato do finding anterior precisa estar explicitamente registrado
    em ``run_input_fact`` no run atual.

    Args:
        db: Pool de conexões do Argus.
        captured: Captura atual, usada para limitar a busca às versões de
            fatos que este run realmente observou.

    Returns:
        Findings anteriores concluídos e disponíveis no instante simulado da
        captura, preservando seus identificadores persistidos.
    """
    rows = db.fetch_all(
        """
        SELECT DISTINCT ON (a.anomaly_id)
               a.anomaly_id, a.observed, a.expected, a.direction, a.deviation,
               a.z, a.strength, a.baseline_snapshot, i.role, f.*
          FROM detect.run_input_fact i
          JOIN silver.analysis_fact_version f
            ON f.fact_key = i.fact_key AND f.version_lsn = i.version_lsn
          JOIN detect.anomaly a
            ON a.fact_key = f.fact_key AND a.version_lsn = f.version_lsn
          JOIN detect.run historical_run ON historical_run.run_id = a.run_id
          JOIN detect.run current_run ON current_run.run_id = i.run_id
         WHERE i.run_id = %s
           AND a.run_id <> %s
           AND historical_run.status = 'completed'
           AND historical_run.manifest_hash = current_run.manifest_hash
           AND historical_run.stream_key = current_run.stream_key
           AND a.available_at <= current_run.sim_now
         ORDER BY a.anomaly_id
        """,
        (captured.claim.run_id, captured.claim.run_id),
    )
    return tuple(
        Anomaly(
            fact=_fact(dict(row)),
            observed=row["observed"],
            expected=row["expected"],
            direction=row["direction"],
            deviation=row["deviation"],
            z=row["z"],
            strength=row["strength"],
            baseline_snapshot=dict(row["baseline_snapshot"] or {}),
            persisted_id=row["anomaly_id"],
        )
        for row in rows
    )


def _quality_finding_id(run_id: int, source: str) -> int:
    """Id deterministico para o finding de qualidade de uma fonte num run.

    Derivado do par (run, fonte) em vez de vir de uma sequence: o mesmo run
    reexecutado precisa produzir o mesmo id, ou o `ON CONFLICT` da gravacao
    duplicaria o finding em vez de atualiza-lo.

    Sete bytes, e nao oito: o oitavo levaria o valor alem do `bigint` com sinal
    do PostgreSQL na metade das vezes.

    Args:
        run_id (int): Execucao.
        source (str): Fonte avaliada.

    Returns:
        int: Identificador estavel, positivo.
    """
    digest = hashlib.sha256(f"{run_id}:{source}".encode()).digest()
    return int.from_bytes(digest[:7], "big")


def persist_result(
    db: Database,
    captured: CapturedWork,
    result: AnalysisResult,
    *,
    duration_ms: int,
) -> None:
    """Grava tudo que o ciclo produziu, numa transacao so.

    Roda dentro de `commit_protegido`, que revalida o `fencing_token` antes do
    commit. Um worker que perdeu a posse no meio do ciclo falha aqui, em vez de
    publicar por cima do resultado de quem assumiu o trabalho.

    Args:
        db (Database): Conexao com o banco.
        captured (CapturedWork): O trabalho analisado.
        result (AnalysisResult): Anomalias, baselines, qualidade e hipoteses.
        duration_ms (int): Duracao do ciclo, para a estatistica do run.

    Returns:
        None: As anomalias, baselines, findings e hipóteses são persistidos
        dentro da transação protegida.
    """
    claim = captured.claim
    with commit_protegido(db, claim) as conn, conn.cursor(row_factory=dict_row) as cur:
        for (
            source,
            entity,
            metric,
            hour_brt,
        ), baseline in result.baseline_updates.items():
            cur.execute(
                """
                INSERT INTO detect.baseline_state (
                  manifest_hash, stream_key, source, entity, metric, hour_brt,
                  mean, variance, n, last_event_at, updated_run_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (manifest_hash, stream_key, source, entity, metric, hour_brt)
                DO UPDATE SET mean = EXCLUDED.mean, variance = EXCLUDED.variance,
                              n = EXCLUDED.n, last_event_at = EXCLUDED.last_event_at,
                              updated_run_id = EXCLUDED.updated_run_id
                """,
                (
                    claim.manifest_hash,
                    _stream_key(conn, claim.run_id),
                    source,
                    entity,
                    metric,
                    hour_brt,
                    baseline.mean,
                    baseline.variance,
                    baseline.n,
                    baseline.last_event_at,
                    claim.run_id,
                ),
            )

        new_anomaly_ids: dict[tuple[str, int], int] = {}
        for anomaly in result.anomalies:
            cur.execute(
                """
                INSERT INTO detect.anomaly (
                  run_id, bucket_ts, source, entity, metric, z, score, n_sources,
                  fact_key, version_lsn, observed, expected, direction, deviation,
                  strength, available_at, sample_size, baseline_snapshot
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING anomaly_id
                """,
                (
                    claim.run_id,
                    anomaly.fact.event_start,
                    anomaly.fact.source,
                    anomaly.fact.entity,
                    anomaly.fact.metric,
                    anomaly.z,
                    100 * anomaly.strength,
                    anomaly.fact.fact_key,
                    anomaly.fact.version_lsn,
                    anomaly.observed,
                    anomaly.expected,
                    anomaly.direction,
                    anomaly.deviation,
                    anomaly.strength,
                    anomaly.fact.available_at,
                    anomaly.fact.sample_size,
                    Jsonb(anomaly.baseline_snapshot),
                ),
            )
            new_anomaly_ids[(anomaly.fact.fact_key, anomaly.fact.version_lsn)] = (
                cur.fetchone()["anomaly_id"]
            )

        def finding_id(index: int) -> int:
            """Resolve o id de uma anomalia, ja gravada ou recem-inserida.

            Args:
                index (int): Posicao em `result.finding_anomalies`.

            Returns:
                int: O id persistido. Anomalia herdada de um run anterior ja tem
                    `persisted_id`; a nova so ganha id no INSERT desta
                    transacao, e e dai que ele vem.
            """
            anomaly = result.finding_anomalies[index]
            if anomaly.persisted_id is not None:
                return anomaly.persisted_id
            return new_anomaly_ids[(anomaly.fact.fact_key, anomaly.fact.version_lsn)]

        cur.execute(
            """
            INSERT INTO gold.source_quality_run (run_id, window_start, window_end)
            VALUES (%s, %s, %s)
            """,
            (claim.run_id, captured.window_start, captured.window_end),
        )
        for item in result.quality:
            cur.execute(
                """
                INSERT INTO gold.source_quality (
                  source, run_id, expected_cadence, last_observation_at,
                  freshness, completeness, validity, consistency, quality_score,
                  status, expected_buckets, observed_buckets, details
                ) VALUES (%s, %s, %s * interval '1 second', %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item.source,
                    claim.run_id,
                    item.expected_cadence_seconds,
                    item.last_observation_at,
                    item.freshness,
                    item.completeness,
                    item.validity,
                    item.consistency,
                    item.quality_score,
                    item.status,
                    item.expected_buckets,
                    item.observed_buckets,
                    Jsonb(item.details),
                ),
            )

        family_counts: dict[str, int] = {}
        status_counts = defaultdict(int)
        for hypothesis in result.hypotheses:
            family_counts[hypothesis.family] = family_counts.get(hypothesis.family, 0) + 1
            status_counts[hypothesis.evaluation_status] += 1
            cur.execute(
                """
                INSERT INTO gold.finding_group (
                  run_id, group_key, window_start, window_end, scope
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (run_id, group_key) DO UPDATE SET scope = EXCLUDED.scope
                RETURNING group_id
                """,
                (
                    claim.run_id,
                    hypothesis.lineage_key,
                    hypothesis.effect_start,
                    hypothesis.effect_end,
                    Jsonb(hypothesis.scope),
                ),
            )
            group_id = cur.fetchone()["group_id"]
            for index in hypothesis.anomaly_indexes:
                cur.execute(
                    """
                    INSERT INTO gold.finding_group_member
                      (group_id, finding_kind, finding_id)
                    VALUES (%s, 'anomaly', %s) ON CONFLICT DO NOTHING
                    """,
                    (group_id, finding_id(index)),
                )

            cur.execute(
                """
                SELECT hypothesis_id, revision
                  FROM gold.hypothesis
                 WHERE lineage_key = %s
                 ORDER BY revision DESC LIMIT 1
                 FOR UPDATE
                """,
                (hypothesis.lineage_key,),
            )
            previous = cur.fetchone()
            revision = previous["revision"] + 1 if previous else 1
            cur.execute(
                """
                INSERT INTO gold.hypothesis (
                  run_id, group_id, family, kind, title, summary, scope,
                  effect_start, effect_end, score, coverage, confidence,
                  evaluation_status, contradiction_strength, dedup_key,
                  lineage_key, revision, supersedes_hypothesis_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s,
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING hypothesis_id
                """,
                (
                    claim.run_id,
                    group_id,
                    hypothesis.family,
                    hypothesis.kind,
                    hypothesis.title,
                    hypothesis.summary,
                    Jsonb(hypothesis.scope),
                    hypothesis.effect_start,
                    hypothesis.effect_end,
                    hypothesis.score,
                    hypothesis.coverage,
                    hypothesis.confidence,
                    hypothesis.evaluation_status,
                    hypothesis.contradiction_strength,
                    hypothesis.dedup_key,
                    hypothesis.lineage_key,
                    revision,
                    previous["hypothesis_id"] if previous else None,
                ),
            )
            hypothesis_id = cur.fetchone()["hypothesis_id"]

            for position, index in enumerate(hypothesis.anomaly_indexes):
                cur.execute(
                    """
                    INSERT INTO gold.hypothesis_finding
                      (hypothesis_id, finding_kind, finding_id, role)
                    VALUES (%s, 'anomaly', %s, %s)
                    """,
                    (
                        hypothesis_id,
                        finding_id(index),
                        "subject" if position == 0 else "supporting",
                    ),
                )
            if hypothesis.kind == "data_quality":
                source = str(hypothesis.scope["source"])
                # Nome proprio: reusar `finding_id` aqui rebindaria a funcao
                # homonima definida acima para um int, e a proxima hipotese com
                # anomalia no mesmo run quebraria com "int object is not callable".
                quality_id = _quality_finding_id(claim.run_id, source)
                cur.execute(
                    """
                    INSERT INTO gold.finding_group_member
                      (group_id, finding_kind, finding_id)
                    VALUES (%s, 'source_quality', %s) ON CONFLICT DO NOTHING
                    """,
                    (group_id, quality_id),
                )
                cur.execute(
                    """
                    INSERT INTO gold.hypothesis_finding
                      (hypothesis_id, finding_kind, finding_id, role)
                    VALUES (%s, 'source_quality', %s, 'subject')
                    """,
                    (hypothesis_id, quality_id),
                )

            for feature in hypothesis.features:
                cur.execute(
                    """
                    INSERT INTO gold.hypothesis_feature (
                      hypothesis_id, feature, applicability, value, weight,
                      contribution, explanation
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        hypothesis_id,
                        feature.name,
                        feature.applicability,
                        feature.value,
                        feature.weight,
                        feature.contribution,
                        feature.explanation,
                    ),
                )
            for evidence in hypothesis.evidence:
                fact = evidence.fact
                cur.execute(
                    """
                    INSERT INTO gold.hypothesis_evidence (
                      hypothesis_id, fact_key, version_lsn, role, polarity,
                      source, entity, metric, event_at, available_at, observed,
                      expected, strength, quality, explanation, attributes
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                              %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        hypothesis_id,
                        fact.fact_key if fact else None,
                        fact.version_lsn if fact else None,
                        evidence.role,
                        evidence.polarity,
                        fact.source if fact else None,
                        fact.entity if fact else None,
                        fact.metric if fact else None,
                        fact.event_start if fact else None,
                        fact.available_at if fact else None,
                        evidence.observed,
                        evidence.expected,
                        evidence.strength,
                        evidence.quality,
                        evidence.explanation,
                        Jsonb(evidence.attributes),
                    ),
                )

        cur.execute(
            """
            INSERT INTO gold.hypothesis_run_stats (
              run_id, input_rows, anomalies, candidates_prefiltered,
              candidates_evaluated, candidates_truncated, generated,
              insufficient_evidence, discarded, duration_ms, truncated, family_counts
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                claim.run_id,
                len(captured.facts),
                len(result.anomalies),
                result.candidates_prefiltered,
                result.candidates_evaluated,
                result.candidates_truncated,
                status_counts["generated"],
                status_counts["insufficient_evidence"],
                status_counts["discarded"],
                duration_ms,
                result.candidates_truncated > 0,
                Jsonb(family_counts),
            ),
        )
        cur.execute(
            """
            UPDATE detect.analysis_cursor
               SET last_completed_checkpoint_id = %s,
                   last_ready_through = %s,
                   last_source_lsn = %s,
                   active_run_id = NULL,
                   updated_at = clock_timestamp()
             WHERE manifest_hash = %s AND stream_key = %s
               AND active_run_id = %s
            """,
            (
                claim.checkpoint_id,
                claim.sim_now,
                claim.input_lsn,
                claim.manifest_hash,
                _stream_key(conn, claim.run_id),
                claim.run_id,
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError("cursor de analise deixou de pertencer ao run")


def _stream_key(conn: Any, run_id: int) -> str:
    """Le a `stream_key` de um run usando a conexao ja aberta.

    Recebe a conexao, e nao o `Database`, de proposito: durante `persist_result`
    a leitura precisa acontecer DENTRO da mesma transacao protegida pelo
    fencing. Pegar outra conexao do pool leria fora dela.

    Args:
        conn (Any): Conexao da transacao em curso.
        run_id (int): Execucao consultada.

    Returns:
        str: A chave do fluxo.
    """
    row = conn.execute(
        "SELECT stream_key FROM detect.run WHERE run_id = %s", (run_id,)
    ).fetchone()
    return row[0]


def promote_manifest(
    db: Database,
    manifest_hash: str,
    gate_metrics: dict[str, Any],
    *,
    withdraw: bool = False,
) -> None:
    """Publica ou retira um manifesto, por evento append-only.

    O motor sobe em modo sombra: as views de hipotese ficam vazias ate o evento
    `published` (AGENTS.md, regra 6). `withdrawn` volta a ocultar SEM apagar
    nada -- o historico de execucoes continua auditavel, e uma retirada pode ser
    revertida por um `published` novo.

    Args:
        db (Database): Conexao com o banco.
        manifest_hash (str): Manifesto afetado.
        gate_metrics (dict[str, Any]): Metricas que justificaram a decisao,
            gravadas junto com o evento.
        withdraw (bool): `True` retira; `False` publica.

    Returns:
        None: A publicação ou retirada é registrada como evento append-only.
    """
    action = "withdrawn" if withdraw else "published"
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.manifest_publication_event
              (manifest_hash, action, gate_metrics)
            VALUES (%s, %s, %s)
            """,
            (manifest_hash, action, Jsonb(gate_metrics)),
        )
