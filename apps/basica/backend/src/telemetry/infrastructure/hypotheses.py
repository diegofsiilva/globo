"""Repositorio das views publicas de hipoteses e da funcao estreita de feedback."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from telemetry.domain.exceptions import ConflictError


def _encode_cursor(row: dict[str, Any]) -> str:
    payload = json.dumps(
        [row["score"], row["effect_start"].isoformat(), row["hypothesis_id"]],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[float, datetime, int]:
    try:
        padded = value + "=" * (-len(value) % 4)
        score, effect_start, hypothesis_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        return float(score), datetime.fromisoformat(effect_start), int(hypothesis_id)
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeDecodeError,
    ) as error:
        raise ValueError("cursor invalido") from error


class HypothesisRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def runs(self, *, limit: int = 50, before_run_id: int | None = None) -> list[dict]:
        where = sql.SQL("TRUE")
        params: list[Any] = []
        if before_run_id is not None:
            where = sql.SQL("run_id < %s")
            params.append(before_run_id)
        return self._all(
            sql.SQL(
                """
                SELECT * FROM gold.v_hypothesis_run
                 WHERE {where}
                 ORDER BY run_id DESC
                 LIMIT %s
                """
            ).format(where=where),
            [*params, limit],
        )

    def list(
        self,
        *,
        family: str | None = None,
        kind: str | None = None,
        confidence: str | None = None,
        review_status: str | None = None,
        source: str | None = None,
        entity: str | None = None,
        run_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        clauses = [sql.SQL("TRUE")]
        params: list[Any] = []
        for column, value in (
            ("family", family),
            ("kind", kind),
            ("confidence", confidence),
            ("review_status", review_status),
            ("run_id", run_id),
        ):
            if value is not None:
                clauses.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
                params.append(value)
        if since is not None:
            clauses.append(sql.SQL("effect_start >= %s"))
            params.append(since)
        if until is not None:
            clauses.append(sql.SQL("effect_start <= %s"))
            params.append(until)
        if source is not None or entity is not None:
            evidence = [sql.SQL("e.hypothesis_id = h.hypothesis_id")]
            if source is not None:
                evidence.append(sql.SQL("e.source = %s"))
                params.append(source)
            if entity is not None:
                evidence.append(sql.SQL("e.entity = %s"))
                params.append(entity)
            clauses.append(
                sql.SQL("EXISTS (SELECT 1 FROM gold.v_hypothesis_evidence e WHERE {})").format(
                    sql.SQL(" AND ").join(evidence)
                )
            )
        if cursor:
            cursor_score, cursor_start, cursor_id = _decode_cursor(cursor)
            clauses.append(sql.SQL("(score, effect_start, hypothesis_id) < (%s, %s, %s)"))
            params.extend([cursor_score, cursor_start, cursor_id])

        rows = self._all(
            sql.SQL(
                """
                SELECT h.* FROM gold.v_hypothesis h
                 WHERE {where}
                 ORDER BY score DESC, effect_start DESC, hypothesis_id DESC
                 LIMIT %s
                """
            ).format(where=sql.SQL(" AND ").join(clauses)),
            [*params, limit + 1],
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        return {
            "items": items,
            "next_cursor": _encode_cursor(items[-1]) if has_more and items else None,
        }

    def detail(self, hypothesis_id: int) -> dict[str, Any] | None:
        row = self._one(
            "SELECT * FROM gold.v_hypothesis_detail WHERE hypothesis_id = %s",
            [hypothesis_id],
        )
        if row is None:
            return None
        row["evidence"] = self._all(
            """
            SELECT * FROM gold.v_hypothesis_evidence
             WHERE hypothesis_id = %s
             ORDER BY polarity, event_at, evidence_id
            """,
            [hypothesis_id],
        )
        return row

    def submit_feedback(
        self,
        *,
        hypothesis_id: int,
        verdict: str,
        note: str | None,
        reviewer_ref: str | None,
        idempotency_key: UUID,
        request_id: str | None,
    ) -> dict[str, Any] | None:
        try:
            return self._one(
                """
                SELECT * FROM gold.submit_hypothesis_feedback(%s, %s, %s, %s, %s, %s)
                """,
                [hypothesis_id, verdict, note, reviewer_ref, idempotency_key, request_id],
            )
        except Exception as error:
            if getattr(error, "sqlstate", None) == "P0002":
                return None
            if getattr(error, "sqlstate", None) == "P0003":
                raise ConflictError("idempotency_key ja usada com outro payload") from error
            raise

    def _all(self, query, params: list[Any]) -> list[dict[str, Any]]:
        with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchall()

    def _one(self, query, params: list[Any]) -> dict[str, Any] | None:
        rows = self._all(query, params)
        return rows[0] if rows else None
