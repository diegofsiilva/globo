"""CLI: repete as consultas de um caso sintetico e imprime o registro JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from argus_agente.leitor import run_case


def main() -> None:
    """Imprime um registro JSON reproduzível a partir de um caso sintético."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    print(json.dumps(run_case(case), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
