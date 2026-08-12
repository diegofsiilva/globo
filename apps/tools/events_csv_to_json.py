"""Converte os exports CSV de eventos do BI no payload JSON que a API de ingestao aceita.

Os arquivos em `Downloads/Events` sao exports tabulares ("Requests (#) - Domain"),
um schema de colunas diferente por tipo de evento. A API de ingestao trabalha com
um envelope unico em snake_case, entao este script faz a ponte:

  - "App Bucket"            -> app_bucket
  - "Capabilities Cursor"   -> capabilities_cursor
  - "Route Params" (string) -> objeto JSON
  - "July 13, 2026 20:04:44" -> "2026-07-13T23:04:44Z"

O timestamp do export nao tem timezone. Comparando o evento `request` com o header
`date` da propria resposta HTTP (20:04:44 no evento vs 23:04:44 GMT no header)
fica claro que o BI renderiza em America/Sao_Paulo, entao assumimos UTC-3 e
normalizamos para UTC. Ver EVENT_TZ.

Uso:
    python apps/tools/events_csv_to_json.py --src ~/Downloads/Events --out apps/worker/tests/fixtures
    python apps/tools/events_csv_to_json.py --src ~/Downloads/Events --stdout
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# --------------------------------------------------------------------------- #
# Normalizacao de nomes de coluna
# --------------------------------------------------------------------------- #

EVENT_TZ = ZoneInfo("America/Sao_Paulo")

# O export escreve "Dobly"; o campo correto e Dolby. Corrigimos na fronteira para
# nao carregar o typo do fornecedor para dentro do DynamoDB.
COLUMN_OVERRIDES = {
    "Capabilities Audio Dobly Atmos": "capabilities_audio_dolby_atmos",
}

# Colunas cujo conteudo e JSON serializado dentro do CSV.
JSON_COLUMNS = {
    "Route Params",
    "Request Headers",
    "Response Headers",
}

BOOL_VALUES = {"true": True, "false": False}

RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def to_snake(column: str) -> str:
    """"App Model Year" -> "app_model_year"."""
    if column in COLUMN_OVERRIDES:
        return COLUMN_OVERRIDES[column]
    return RE_NON_ALNUM.sub("_", column.strip().lower()).strip("_")


def parse_timestamp(raw: str) -> str:
    """"July 13, 2026 20:04:44" (America/Sao_Paulo) -> "2026-07-13T23:04:44Z"."""
    naive = datetime.strptime(raw.strip(), "%B %d, %Y %H:%M:%S")
    utc = naive.replace(tzinfo=EVENT_TZ).astimezone(ZoneInfo("UTC"))
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def coerce(column: str, raw: str):
    """Converte o valor bruto do CSV para o tipo JSON adequado."""
    value = raw.strip()
    if value == "":
        return None
    if column in JSON_COLUMNS:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Preserva o texto original em vez de descartar: o worker marca o
            # evento como parcialmente invalido, mas o dado bruto nao se perde.
            return value
    if column == "Timestamp":
        return parse_timestamp(value)
    low = value.lower()
    if low in BOOL_VALUES:
        return BOOL_VALUES[low]
    if column == "Duration":
        return float(value)
    if column == "Request Status":
        return int(value)
    if column == "Device Model Year" and value.isdigit():
        return int(value)
    return value


def convert_row(row: dict[str, str]) -> dict:
    """Uma linha do CSV -> um evento JSON canonico."""
    event: dict = {}
    for column, raw in row.items():
        if column is None:
            continue
        value = coerce(column, raw if raw is not None else "")
        if value is None:
            continue  # campo ausente e omitido, nao vira null
        event[to_snake(column)] = value
    return event


def convert_file(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return [convert_row(row) for row in csv.DictReader(fh)]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True, help="pasta com os CSVs")
    ap.add_argument("--out", type=Path, help="pasta destino dos .json")
    ap.add_argument(
        "--stdout",
        action="store_true",
        help="imprime um array JSON com todos os eventos em vez de gravar arquivos",
    )
    args = ap.parse_args()

    if not args.src.is_dir():
        print(f"erro: {args.src} nao e uma pasta", file=sys.stderr)
        return 1

    files = sorted(args.src.glob("*.csv"))
    if not files:
        print(f"erro: nenhum CSV em {args.src}", file=sys.stderr)
        return 1

    events: list[dict] = []
    for path in files:
        events.extend(convert_file(path))

    if args.stdout or not args.out:
        json.dump(events, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    # Um arquivo por tipo de evento, com sufixo quando houver repetidos.
    seen: dict[str, int] = {}
    for event in events:
        name = event.get("event_name", "unknown")
        seen[name] = seen.get(name, 0) + 1
        suffix = "" if seen[name] == 1 else f"_{seen[name]}"
        dest = args.out / f"{name}{suffix}.json"
        dest.write_text(
            json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  {dest.relative_to(Path.cwd()) if dest.is_absolute() else dest}")

    print(f"\n{len(events)} eventos convertidos de {len(files)} arquivos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
