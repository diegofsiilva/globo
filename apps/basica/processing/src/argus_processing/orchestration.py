"""Coordenacao transacional da analise de checkpoints Gold.

O advisory lock existe somente durante o claim. O trabalho demorado acontece
fora de transacao e e protegido por lease e fencing persistidos no PostgreSQL.
A publicacao dos resultados usa :func:`commit_protegido`: validar a posse,
inserir filhos e concluir o run fazem parte do mesmo commit curto.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from argus_common import Database
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

# Numero fixo e documentado, dentro do intervalo bigint assinado do PostgreSQL.
# Todas as replicas disputam a mesma chave apenas durante a secao curta de claim.
CLAIM_ADVISORY_LOCK_KEY = 4_702_917_301_778_411

_ACTIVE_STATUSES = frozenset({"claimed", "running", "committing"})


class CoordinationError(RuntimeError):
    """Erro de contrato da coordenacao de analise."""


class FencingRejected(CoordinationError):
    """A tentativa perdeu o lease ou deixou de possuir o fencing token ativo."""


@dataclass(frozen=True, slots=True)
class WorkClaim:
    """Fotografia da posse de uma unidade logica de analise."""

    run_id: int
    checkpoint_id: int
    manifest_hash: str
    sim_now: dt.datetime
    claimed_by: str
    lease_expires_at: dt.datetime
    heartbeat_at: dt.datetime
    fencing_token: int
    attempt: int
    retry_of: int | None
    input_lsn: int
    status: str


def _validar_texto(nome: str, valor: str) -> str:
    """Valida e normaliza identificadores textuais da coordenacao."""
    normalizado = valor.strip()
    if not normalizado:
        raise ValueError(f"{nome} nao pode ser vazio")
    return normalizado


def _validar_lease(lease_seconds: int) -> int:
    """Garante que o lease sempre crie uma janela operacional positiva."""
    if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int):
        raise TypeError("lease_seconds precisa ser inteiro")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds precisa ser maior que zero")
    return lease_seconds


def _claim_from_row(row: Mapping[str, Any]) -> WorkClaim:
    """Converte uma linha de ``detect.run`` no contrato Python imutavel."""
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


def reivindicar_trabalho(
    db: Database,
    *,
    worker_id: str,
    manifest_hash: str,
    lease_seconds: int = 60,
    detector: str = "argus-rules",
    params: Mapping[str, Any] | None = None,
    input_digest: str | None = None,
) -> WorkClaim | None:
    """Reivindica o checkpoint Gold mais recente para um manifesto.

    O lock global e transacional. Quando outra replica esta na pequena secao
    critica ou ja possui um lease valido, a funcao devolve ``None`` sem esperar
    o termino do processamento.

    Args:
        db: Pool de conexoes do Argus.
        worker_id: Identificador unico da replica/tentativa.
        manifest_hash: Identidade logica das regras e configuracoes.
        lease_seconds: Duracao inicial do lease em tempo real.
        detector: Nome legivel do detector que produzira o run.
        params: Parametros auditaveis do run.
        input_digest: Hash opcional da captura de entrada.

    Returns:
        A posse criada, ou ``None`` quando nao ha trabalho reivindicavel.
    """
    worker_id = _validar_texto("worker_id", worker_id)
    manifest_hash = _validar_texto("manifest_hash", manifest_hash)
    detector = _validar_texto("detector", detector)
    lease_seconds = _validar_lease(lease_seconds)

    with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT pg_try_advisory_xact_lock(%s) AS adquirido",
            (CLAIM_ADVISORY_LOCK_KEY,),
        )
        if not cur.fetchone()["adquirido"]:
            return None

        cur.execute(
            """
            SELECT gc.checkpoint_id, gc.sim_run_id, gc.source_lsn,
                   sim.now() AS sim_now, clock_timestamp() AS agora
              FROM etl.gold_checkpoint AS gc
             ORDER BY gc.checkpoint_id DESC
             LIMIT 1
            """
        )
        checkpoint = cur.fetchone()
        if checkpoint is None:
            return None

        cur.execute(
            """
            SELECT wc.run_id, wc.lease_expires_at, wc.fencing_token,
                   r.status, r.attempt
              FROM detect.work_claim AS wc
              JOIN detect.run AS r ON r.run_id = wc.run_id
             WHERE wc.checkpoint_id = %s
               AND wc.manifest_hash = %s
             FOR UPDATE OF wc, r
            """,
            (checkpoint["checkpoint_id"], manifest_hash),
        )
        anterior = cur.fetchone()

        retry_of = None
        attempt = 1
        if anterior is not None:
            if anterior["status"] == "completed":
                return None
            if (
                anterior["status"] in _ACTIVE_STATUSES
                and anterior["lease_expires_at"] > checkpoint["agora"]
            ):
                return None

            retry_of = anterior["run_id"]
            attempt = anterior["attempt"] + 1
            if anterior["status"] in _ACTIVE_STATUSES:
                cur.execute(
                    """
                    UPDATE detect.run
                       SET status = 'abandoned',
                           finished_at = clock_timestamp(),
                           error_message = COALESCE(
                             error_message,
                             'lease expirado; trabalho assumido por outra tentativa'
                           )
                     WHERE run_id = %s
                    """,
                    (anterior["run_id"],),
                )

        cur.execute("SELECT nextval('detect.fencing_token_seq') AS token")
        fencing_token = cur.fetchone()["token"]
        lease_expires_at = checkpoint["agora"] + dt.timedelta(seconds=lease_seconds)

        cur.execute(
            """
            INSERT INTO detect.run (
              sim_run_id, detector, params, checkpoint_id, manifest_hash,
              sim_now, status, claimed_by, lease_expires_at, heartbeat_at,
              fencing_token, attempt, retry_of, input_lsn, input_digest
            ) VALUES (
              %s, %s, %s, %s, %s,
              %s, 'claimed', %s, %s, %s,
              %s, %s, %s, %s, %s
            )
            RETURNING run_id, checkpoint_id, manifest_hash, sim_now, claimed_by,
                      lease_expires_at, heartbeat_at, fencing_token, attempt,
                      retry_of, input_lsn, status
            """,
            (
                checkpoint["sim_run_id"],
                detector,
                Jsonb(dict(params or {})),
                checkpoint["checkpoint_id"],
                manifest_hash,
                checkpoint["sim_now"],
                worker_id,
                lease_expires_at,
                checkpoint["agora"],
                fencing_token,
                attempt,
                retry_of,
                checkpoint["source_lsn"],
                input_digest,
            ),
        )
        novo = cur.fetchone()

        if anterior is None:
            cur.execute(
                """
                INSERT INTO detect.work_claim (
                  checkpoint_id, manifest_hash, run_id, claimed_by,
                  lease_expires_at, heartbeat_at, fencing_token
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    novo["checkpoint_id"],
                    novo["manifest_hash"],
                    novo["run_id"],
                    novo["claimed_by"],
                    novo["lease_expires_at"],
                    novo["heartbeat_at"],
                    novo["fencing_token"],
                ),
            )
        else:
            cur.execute(
                """
                UPDATE detect.work_claim
                   SET run_id = %s,
                       claimed_by = %s,
                       lease_expires_at = %s,
                       heartbeat_at = %s,
                       fencing_token = %s,
                       updated_at = clock_timestamp()
                 WHERE checkpoint_id = %s
                   AND manifest_hash = %s
                """,
                (
                    novo["run_id"],
                    novo["claimed_by"],
                    novo["lease_expires_at"],
                    novo["heartbeat_at"],
                    novo["fencing_token"],
                    novo["checkpoint_id"],
                    novo["manifest_hash"],
                ),
            )

        return _claim_from_row(novo)


def _bloquear_posse(cur: Any, claim: WorkClaim) -> Mapping[str, Any] | None:
    """Bloqueia claim e run atuais na mesma ordem usada por takeover."""
    cur.execute(
        """
        SELECT r.status, wc.claimed_by, wc.lease_expires_at,
               wc.heartbeat_at, wc.fencing_token,
               clock_timestamp() AS agora
          FROM detect.work_claim AS wc
          JOIN detect.run AS r ON r.run_id = wc.run_id
         WHERE wc.checkpoint_id = %s
           AND wc.manifest_hash = %s
           AND wc.run_id = %s
           AND wc.fencing_token = %s
         FOR UPDATE OF wc, r
        """,
        (
            claim.checkpoint_id,
            claim.manifest_hash,
            claim.run_id,
            claim.fencing_token,
        ),
    )
    return cur.fetchone()


def _posse_valida(row: Mapping[str, Any] | None, claim: WorkClaim) -> bool:
    """Confere owner, token e validade temporal depois de adquirir os locks."""
    return bool(
        row is not None
        and row["claimed_by"] == claim.claimed_by
        and row["fencing_token"] == claim.fencing_token
        and row["lease_expires_at"] > row["agora"]
    )


def iniciar_trabalho(db: Database, claim: WorkClaim) -> bool:
    """Move uma posse valida de ``claimed`` para ``running``."""
    with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        atual = _bloquear_posse(cur, claim)
        if not _posse_valida(atual, claim) or atual["status"] != "claimed":
            return False
        cur.execute(
            """
            UPDATE detect.run
               SET status = 'running', started_at = clock_timestamp()
             WHERE run_id = %s
            """,
            (claim.run_id,),
        )
        return True


def renovar_lease(db: Database, claim: WorkClaim, *, lease_seconds: int = 60) -> bool:
    """Renova heartbeat e lease sem emitir outro fencing token."""
    lease_seconds = _validar_lease(lease_seconds)
    with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        atual = _bloquear_posse(cur, claim)
        if not _posse_valida(atual, claim) or atual["status"] not in {
            "claimed",
            "running",
        }:
            return False

        cur.execute(
            """
            SELECT clock_timestamp() AS heartbeat_at,
                   clock_timestamp() + %s * interval '1 second' AS lease_expires_at
            """,
            (lease_seconds,),
        )
        tempos = cur.fetchone()
        cur.execute(
            """
            UPDATE detect.run
               SET heartbeat_at = %s, lease_expires_at = %s
             WHERE run_id = %s
            """,
            (tempos["heartbeat_at"], tempos["lease_expires_at"], claim.run_id),
        )
        cur.execute(
            """
            UPDATE detect.work_claim
               SET heartbeat_at = %s,
                   lease_expires_at = %s,
                   updated_at = clock_timestamp()
             WHERE run_id = %s
            """,
            (tempos["heartbeat_at"], tempos["lease_expires_at"], claim.run_id),
        )
        return True


@contextmanager
def commit_protegido(db: Database, claim: WorkClaim) -> Iterator[Connection]:
    """Abre a transacao curta de persistencia protegida por fencing.

    O chamador insere os resultados usando a conexao entregue pelo contexto.
    Qualquer excecao faz rollback do estado ``committing`` e das linhas filhas.
    Um token antigo falha antes de entregar a conexao ao chamador.

    Raises:
        FencingRejected: Quando o claim nao e mais o proprietario ativo.
    """
    with db.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            atual = _bloquear_posse(cur, claim)
            if not _posse_valida(atual, claim) or atual["status"] != "running":
                raise FencingRejected(f"run {claim.run_id} perdeu lease ou fencing token")
            cur.execute(
                "UPDATE detect.run SET status = 'committing' WHERE run_id = %s",
                (claim.run_id,),
            )

        yield conn

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE detect.run
                   SET status = 'completed',
                       finished_at = clock_timestamp(),
                       error_message = NULL
                 WHERE run_id = %s
                   AND status = 'committing'
                   AND fencing_token = %s
                """,
                (claim.run_id, claim.fencing_token),
            )
            if cur.rowcount != 1:
                raise FencingRejected(
                    f"run {claim.run_id} mudou durante o commit protegido"
                )
            cur.execute(
                """
                UPDATE detect.work_claim
                   SET updated_at = clock_timestamp()
                 WHERE run_id = %s
                   AND fencing_token = %s
                """,
                (claim.run_id, claim.fencing_token),
            )


def falhar_trabalho(db: Database, claim: WorkClaim, error_message: str) -> bool:
    """Encerra como ``failed`` uma tentativa que ainda possui lease e token."""
    error_message = _validar_texto("error_message", error_message)
    with db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        atual = _bloquear_posse(cur, claim)
        if not _posse_valida(atual, claim) or atual["status"] not in {
            "claimed",
            "running",
        }:
            return False
        cur.execute(
            """
            UPDATE detect.run
               SET status = 'failed',
                   finished_at = clock_timestamp(),
                   error_message = %s
             WHERE run_id = %s
            """,
            (error_message, claim.run_id),
        )
        cur.execute(
            """
            UPDATE detect.work_claim
               SET updated_at = clock_timestamp()
             WHERE run_id = %s
            """,
            (claim.run_id,),
        )
        return True
