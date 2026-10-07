"""Compila Go e compara todas as saídas com Python, fora de qualquer cronômetro."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

from argus_processing.catalog import Catalog
from benchmarks.contrato import comparar, contagens, executar_ciclo, executar_regras

BASE = Path(__file__).resolve().parent


def verificar(go: str) -> int:
    """Compara os 49 casos e os cinco ciclos; encerra na primeira divergência."""
    catalog = Catalog()
    total = 0
    with tempfile.TemporaryDirectory(prefix="argus-paridade-") as directory:
        binary = Path(directory) / ("paridade.exe" if os.name == "nt" else "paridade")
        subprocess.run(
            [go, "build", "-o", str(binary), "./cmd/paridade"],
            cwd=BASE / "golang",
            check=True,
        )
        for name in ("regras_casos_v1.json", "ciclo_caso_v1.json", "cargas_v1.json"):
            path = BASE / "fixtures" / name
            document = json.loads(path.read_text(encoding="utf-8"))
            if document["catalog_manifest_hash"] != catalog.manifest_hash:
                raise AssertionError(f"{name}: catálogo divergiu")
            output = subprocess.run(
                [
                    str(binary),
                    "-input",
                    str(path),
                    "-catalogs",
                    str(BASE.parent / "src" / "argus_processing" / "catalogs"),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            actual = json.loads(output.stdout)
            expected = {}
            for case in document.get("cases", []):
                result = executar_regras(case, catalog)
                comparar(result, case["expected"], case["id"] + ".python_congelado")
                expected[case["id"]] = result
            cycles = document.get("workloads", [])
            if "case" in document:
                cycles = [document["case"]]
            for case in cycles:
                result = executar_ciclo(case, catalog)
                if "expected" in case:
                    comparar(result, case["expected"], case["id"] + ".python_congelado")
                if "expected_counts" in case:
                    comparar(contagens(case, result), case["expected_counts"])
                expected[case["id"]] = result
            comparar(actual, expected, name)
            total += len(expected)
            print(f"{name}: {len(expected)} saídas completas equivalentes.")
    return total


def main() -> None:
    """Aceita caminho explícito do Go para instalações portáteis."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default=os.environ.get("GO", "go"))
    args = parser.parse_args()
    print(f"Paridade aprovada em {verificar(args.go)} casos/cargas.")


if __name__ == "__main__":
    main()
