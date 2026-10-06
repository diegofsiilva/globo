"""CLI: abre um recorte real do PostgreSQL local e imprime inventario ou consultas."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from argus_agente.banco import load_checkpoint
from argus_agente.leitor import execute_queries


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
