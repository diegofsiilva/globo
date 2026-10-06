"""Abre um recorte real do PostgreSQL local, somente leitura.

Nao escreve no processamento, nao toma posse de cursor e so aceita host local.
A saida e o mesmo `CaseReader` que o executor sintetico usa, de modo que o
agente nao sabe de qual origem veio o recorte.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from argus_agente.leitor import CaseReader

MAX_FACTS = 10_000


def exigir_banco_local(database_url: str) -> None:
    """Recusa destino remoto, inclusive `hostaddr` que prevalece sobre `host`.

    Args:
        database_url (str): String de conexao libpq.

    Raises:
        ValueError: Se o destino nao for o PostgreSQL local.
    """
    destino = conninfo_to_dict(database_url)
    if destino.get("host") not in {"localhost", "127.0.0.1", "::1"} or destino.get(
        "hostaddr"
    ):
        raise ValueError("o piloto aceita apenas PostgreSQL local")


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
        entity (str): Entidade exata que delimita o recorte.
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
    exigir_banco_local(database_url)
    with (
        psycopg.connect(
            database_url, connect_timeout=10, autocommit=True, row_factory=dict_row
        ) as connection,
        connection.transaction(),
    ):
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
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
        # Anterior no tempo, nao no id: o id so ordena se os checkpoints forem
        # publicados em ordem, e nao ha garantia disso.
        previous = connection.execute(
            """
                SELECT ready_through FROM etl.gold_checkpoint
                 WHERE ready_through < %s
                   AND sim_run_id IS NOT DISTINCT FROM %s
                 ORDER BY ready_through DESC LIMIT 1
                """,
            (sim_now, checkpoint["sim_run_id"]),
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
