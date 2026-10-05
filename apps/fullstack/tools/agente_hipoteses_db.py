"""Abre recorte local do agente em PostgreSQL, sem escrever no processamento."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from agente_hipoteses_caso import CaseReader, execute_queries

MAX_FACTS = 10_000

FACTS_SQL = """
WITH latest AS (
  SELECT DISTINCT ON (fact_key)
         fact_key, version_lsn, kind, event_start, event_end, available_at,
         source, entity, metric, dimension_type, dimension_value, value,
         sample_size, is_deleted
    FROM silver.analysis_fact_version
   WHERE version_lsn <= %(input_lsn)s
     AND available_at <= %(sim_now)s
     AND event_start <= %(sim_now)s
     AND entity = %(entity)s
   ORDER BY fact_key, version_lsn DESC
)
SELECT * FROM latest
 WHERE NOT is_deleted
   AND (event_start >= %(window_start)s
        OR (kind = 'context' AND event_end >= %(window_start)s))
 ORDER BY fact_key, version_lsn
 LIMIT %(max_rows)s
"""


def _utc(value: dt.datetime) -> str:
    """Serializa timestamp do PostgreSQL em UTC para o contrato das ferramentas."""
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def load_checkpoint(
    database_url: str,
    checkpoint_id: int,
    entity: str,
    *,
    lookback_minutes: int = 120,
    max_facts: int = MAX_FACTS,
) -> CaseReader:
    """Lê um checkpoint em transação consistente, somente leitura.

    Args:
        database_url (str): Conexão operacional com leitura de `etl` e `silver`.
        checkpoint_id (int): Checkpoint publicado e não futuro.
        entity (str): Entidade exata que delimita o MVA.
        lookback_minutes (int): Janela anterior ao `ready_through`, até um dia.
        max_facts (int): Teto sem truncamento silencioso.

    Returns:
        CaseReader: Recorte imutável, pronto para as três ferramentas.

    Raises:
        ValueError: Quando o recorte não existe, está no futuro ou excede limites.
    """
    if checkpoint_id <= 0 or not entity.strip():
        raise ValueError("checkpoint_id e entity são obrigatórios")
    if not 1 <= lookback_minutes <= 1440:
        raise ValueError("lookback_minutes deve estar entre 1 e 1440")
    if not 1 <= max_facts <= MAX_FACTS:
        raise ValueError("max_facts deve estar entre 1 e 10000")
    host = conninfo_to_dict(database_url).get("host")
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("o piloto aceita apenas PostgreSQL local")
    with psycopg.connect(
        database_url, connect_timeout=10, autocommit=True, row_factory=dict_row
    ) as connection:
        with connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            checkpoint = connection.execute(
                """
                SELECT checkpoint_id, ready_through, source_lsn, sim_run_id
                  FROM etl.gold_checkpoint
                 WHERE checkpoint_id = %s AND ready_through <= sim.now()
                """,
                (checkpoint_id,),
            ).fetchone()
            if checkpoint is None:
                raise ValueError("checkpoint inexistente ou posterior a sim.now()")
            sim_now = checkpoint["ready_through"]
            window_start = sim_now - dt.timedelta(minutes=lookback_minutes)
            previous = connection.execute(
                """
                SELECT ready_through FROM etl.gold_checkpoint
                 WHERE checkpoint_id < %s
                   AND sim_run_id IS NOT DISTINCT FROM %s
                 ORDER BY checkpoint_id DESC LIMIT 1
                """,
                (checkpoint_id, checkpoint["sim_run_id"]),
            ).fetchone()
            subject_start = max(
                window_start, previous["ready_through"] if previous else window_start
            )
            rows = connection.execute(
                FACTS_SQL,
                {
                    "input_lsn": checkpoint["source_lsn"],
                    "sim_now": sim_now,
                    "window_start": window_start,
                    "entity": entity,
                    "max_rows": max_facts + 1,
                },
            ).fetchall()
            if len(rows) > max_facts:
                raise ValueError("recorte excede o teto de fatos; reduza a janela")
    facts = []
    for row in rows:
        fact: dict[str, Any] = dict(row)
        fact["role"] = "subject" if row["event_start"] >= subject_start else "context"
        for field in ("event_start", "event_end", "available_at"):
            if fact[field] is not None:
                fact[field] = _utc(fact[field])
        facts.append(fact)
    case = {
        "case_id": f"checkpoint-{checkpoint_id}-{entity}-{lookback_minutes}m",
        "origin": "database",
        "checkpoint_id": checkpoint_id,
        "sim_now": _utc(sim_now),
        "input_lsn": checkpoint["source_lsn"],
        "facts": facts,
    }
    return CaseReader(case)


def main() -> None:
    """Abre um recorte real e imprime inventário ou consultas declaradas."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-id", type=int, required=True)
    parser.add_argument("--entity", required=True)
    parser.add_argument("--lookback-minutes", type=int, default=120)
    parser.add_argument("--queries", type=Path)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL é necessária")
    reader = load_checkpoint(
        database_url,
        args.checkpoint_id,
        args.entity,
        lookback_minutes=args.lookback_minutes,
    )
    queries = (
        json.loads(args.queries.read_text(encoding="utf-8"))
        if args.queries
        else [{"tool": "inventariar_fatos", "params": {}}]
    )
    result = {
        "origin": "database",
        "checkpoint_id": args.checkpoint_id,
        "entity": args.entity,
        "sim_now": reader.sim_now.isoformat(),
        "input_lsn": reader.input_lsn,
        "recorte_id": reader.recorte_id,
        "pilot_digest": reader.digest,
        "responses": execute_queries(reader, queries),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
