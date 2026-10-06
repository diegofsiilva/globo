"""Exporta a entrada exata de um run deterministico para o agente local.

Somente leitura. O JSON de fatos vai para `saidas/`, ignorado pelo Git.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from argus_agente.banco import exigir_banco_local
from argus_agente.leitor import CaseReader


def main() -> None:
    """Le o run e grava uma fixture local com os mesmos fatos e papeis."""
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id", type=int)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ["DATABASE_URL"]
    exigir_banco_local(url)
    with psycopg.connect(url, row_factory=dict_row) as conn, conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        run = conn.execute(
            """SELECT run_id, checkpoint_id, sim_now, input_lsn, input_rows,
                          input_digest, status
                     FROM detect.run WHERE run_id = %s""",
            (args.run_id,),
        ).fetchone()
        if not run or run["status"] != "completed":
            raise ValueError("run inexistente ou incompleto")
        linhas = conn.execute(
            """SELECT f.fact_key, f.version_lsn, i.role, f.kind, f.event_start,
                          f.event_end, f.available_at, f.source, f.entity, f.metric,
                          f.dimension_type, f.dimension_value, f.value,
                          f.sample_size, f.attributes, f.is_deleted
                     FROM detect.run_input_fact i
                     JOIN silver.analysis_fact_version f
                       ON f.fact_key = i.fact_key AND f.version_lsn = i.version_lsn
                    WHERE i.run_id = %s
                    ORDER BY i.fact_key, i.version_lsn, i.role""",
            (args.run_id,),
        ).fetchall()
    if len(linhas) != run["input_rows"]:
        raise ValueError("quantidade exportada difere de input_rows")
    fatos = []
    for linha in linhas:
        fato = dict(linha)
        for campo in ("event_start", "event_end", "available_at"):
            if fato[campo] is not None:
                fato[campo] = fato[campo].isoformat()
        fatos.append(fato)
    caso = {
        "case_id": f"run-{args.run_id}-checkpoint-{run['checkpoint_id']}",
        "origin": "database",
        "checkpoint_id": run["checkpoint_id"],
        "sim_now": run["sim_now"].isoformat(),
        "input_lsn": run["input_lsn"],
        "nota_de_escopo": "entrada capturada por run deterministico local",
        "facts": fatos,
    }
    leitor = CaseReader(caso)
    if len(leitor.facts) != len(fatos):
        raise ValueError("leitor do agente alterou o conjunto capturado")
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(caso, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "case_id": caso["case_id"],
                "input_rows": len(fatos),
                "input_digest_motor": run["input_digest"],
                "digest_agente": leitor.digest,
                "saida": str(args.saida),
            }
        )
    )


if __name__ == "__main__":
    main()
