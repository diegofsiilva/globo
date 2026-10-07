"""Mede funções Python sobre entradas já carregadas, sem I/O no cronômetro."""

from __future__ import annotations

import argparse
import gc
import json
import os
import platform
from pathlib import Path
from time import get_clock_info, perf_counter_ns

from argus_processing.catalog import Catalog
from argus_processing.detector import detect
from argus_processing.quality import evaluate_quality
from argus_processing.rules import build_candidates, evaluate_candidates
from benchmarks.contrato import data, ler_baselines, ler_fatos


def medir(function, warmups: int, repetitions: int) -> list[int]:
    """Retém a saída até parar o relógio; libera referências fora do intervalo."""
    for _ in range(warmups):
        result = function()
        del result
    samples = []
    for _ in range(repetitions):
        start = perf_counter_ns()
        result = function()
        elapsed = perf_counter_ns() - start
        samples.append(elapsed)
        del result
    return samples


def executar(path: Path, warmups: int, repetitions: int) -> dict:
    """Prepara entradas iguais para as etapas isoladas e o ciclo completo."""
    document = json.loads(path.read_text(encoding="utf-8"))
    case = document["case"]
    catalog = Catalog()
    if document["catalog_manifest_hash"] != catalog.manifest_hash:
        raise ValueError("Manifesto divergente")
    facts, baselines = ler_fatos(case["facts"]), ler_baselines(case["baselines"])
    start, end, sim_end = (
        data(case[k]) for k in ("window_start", "window_end", "simulator_end")
    )

    def quality_stage():
        """Avalia o canário na janela fixa."""
        return evaluate_quality(
            facts, catalog, window_start=start, window_end=end, simulator_end=sim_end
        )

    quality = quality_stage()
    anomalies, _ = detect(facts, baselines, catalog)
    candidates = build_candidates(anomalies, facts, quality, catalog)

    def total_stage():
        """Mantém todos os resultados vivos até concluir o cálculo completo."""
        q = quality_stage()
        a, updates = detect(facts, baselines, catalog)
        c = build_candidates(a, facts, q, catalog)
        h = evaluate_candidates(c, a, q, catalog)
        return q, a, updates, c, h

    stages = {
        "quality": quality_stage,
        "detector": lambda: detect(facts, baselines, catalog),
        "candidates": lambda: build_candidates(anomalies, facts, quality, catalog),
        "scoring": lambda: evaluate_candidates(candidates, anomalies, quality, catalog),
        "total": total_stage,
    }
    return {
        "runtime": platform.python_implementation() + " " + platform.python_version(),
        "gc_enabled": gc.isenabled(),
        "clock": get_clock_info("perf_counter").implementation,
        "clock_resolution_ns": get_clock_info("perf_counter").resolution * 1e9,
        "samples_ns": {
            name: medir(fn, warmups, repetitions) for name, fn in stages.items()
        },
    }


def main() -> None:
    """Espera o controlador aplicar afinidade e ler o pico de RSS antes de sair."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=50)
    args = parser.parse_args()
    if args.warmups < 3 or args.repetitions < 20:
        parser.error("Use ao menos 3 aquecimentos e 20 repetições")
    print(json.dumps({"ready": True, "pid": os.getpid()}), flush=True)
    input()
    print(json.dumps(executar(args.input, args.warmups, args.repetitions)), flush=True)
    input()


if __name__ == "__main__":
    main()
