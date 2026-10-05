"""Controla a rodada local Python × Go e grava amostras e metadados auditáveis."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from benchmarks.medicao.sistema import ambiente, cpu_disponivel, fixar_cpu, pico_rss
from benchmarks.verificar_paridade import verificar

PROCESSING = Path(__file__).resolve().parents[2]
REPO = PROCESSING.parents[2]
BENCHMARKS = PROCESSING / "benchmarks"
STAGES = ("quality", "detector", "candidates", "scoring", "total")


def resumo(samples: list[int]) -> dict:
    """Calcula mediana e p95 nearest rank, preservando nanosegundos no arquivo bruto."""
    if not samples or any(value <= 0 for value in samples):
        raise ValueError("Amostras devem ser tempos positivos")
    return {
        "median_ms": statistics.median(samples) / 1e6,
        "p95_ms": sorted(samples)[math.ceil(0.95 * len(samples)) - 1] / 1e6,
        "min_ms": min(samples) / 1e6,
        "max_ms": max(samples) / 1e6,
    }


def hashes() -> dict:
    """Identifica códigos e entradas, inclusive implementações ainda sem commit."""
    paths = list(BENCHMARKS.rglob("*.py")) + list((BENCHMARKS / "golang").rglob("*.go"))
    paths += list((BENCHMARKS / "fixtures").glob("*.json"))
    paths += [BENCHMARKS / "golang" / "go.mod"]
    paths += [
        PROCESSING / "src" / "argus_processing" / f"{name}.py"
        for name in ("domain", "catalog", "quality", "detector", "rules", "scoring")
    ]
    paths += list((PROCESSING / "src" / "argus_processing" / "catalogs").glob("*.json"))
    return {
        p.relative_to(REPO).as_posix(): hashlib.sha256(
            p.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()
        for p in sorted(paths)
    }


def medir_processo(command: list[str], cpu: int, repetitions: int) -> dict:
    """Executa um filho, fixa sua CPU e captura o pico de RSS antes de liberá-lo."""
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
        "GOGC": "100",
        "GOMEMLIMIT": "off",
        "GOMAXPROCS": "1",
    }
    with (
        tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors,
        subprocess.Popen(
            command,
            cwd=PROCESSING,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            encoding="utf-8",
            env=env,
        ) as process,
    ):
        try:
            ready_line = process.stdout.readline()
            if not ready_line:
                errors.seek(0)
                raise RuntimeError("Processo não iniciou: " + errors.read())
            ready = json.loads(ready_line)
            if ready.get("ready") is not True or not isinstance(ready.get("pid"), int):
                raise RuntimeError("Identificação do processo de cálculo inválida")
            # O python.exe do venv no Windows pode ser um lançador de outro PID.
            # O próprio executor informa quem deve receber afinidade e coleta de RSS.
            worker_pid = ready["pid"]
            fixar_cpu(worker_pid, cpu)
            process.stdin.write("iniciar\n")
            process.stdin.flush()
            line = process.stdout.readline()
            if not line:
                errors.seek(0)
                raise RuntimeError("Processo falhou: " + errors.read())
            result = json.loads(line)
            result["peak_rss_bytes"] = pico_rss(worker_pid)
            result["worker_pid"] = worker_pid
            result["launcher_pid"] = process.pid
            process.communicate("encerrar\n", timeout=30)
            if process.returncode:
                errors.seek(0)
                raise RuntimeError(errors.read())
        except BaseException:
            process.kill()
            process.wait()
            raise
    if set(result["samples_ns"]) != set(STAGES):
        raise ValueError("Etapas medidas divergentes")
    result["summary"] = {}
    for stage, samples in result["samples_ns"].items():
        if len(samples) != repetitions:
            raise ValueError(f"{stage}: quantidade incorreta de amostras")
        result["summary"][stage] = resumo(samples)
    return result


def executar(args) -> dict:
    """Compila antes da medição e compara perfis em processos novos sequenciais."""
    if platform.system() not in {"Windows", "Linux"}:
        raise RuntimeError("Medição de RSS e afinidade disponível para Windows/Linux")
    before = hashes()
    parity_cases = verificar(args.go)
    cpu = cpu_disponivel()
    result = {
        "schema_version": 1,
        "label": args.label,
        "environment": ambiente(),
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "source_files_sha256": before,
        "protocol": {
            "warmups": args.warmups,
            "repetitions": args.repetitions,
            "cpu_affinity": cpu,
            "decision_threshold": None,
            "parity_cases": parity_cases,
            "memory": "process_peak_resident_bytes",
        },
        "workloads": [],
    }
    cycle = json.loads((BENCHMARKS / "fixtures/ciclo_caso_v1.json").read_text("utf-8"))
    loads = json.loads((BENCHMARKS / "fixtures/cargas_v1.json").read_text("utf-8"))
    cases = [cycle["case"], *loads["workloads"]]
    with tempfile.TemporaryDirectory(prefix="argus-medicao-") as directory:
        binary = Path(directory) / ("medir.exe" if os.name == "nt" else "medir")
        subprocess.run(
            [args.go, "build", "-o", str(binary), "./cmd/medir"],
            cwd=BENCHMARKS / "golang",
            check=True,
        )
        for index, case in enumerate(cases):
            path = Path(directory) / "entrada.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "catalog_manifest_hash": cycle["catalog_manifest_hash"],
                        "case": {
                            k: v
                            for k, v in case.items()
                            if k not in ("expected", "expected_counts", "profile")
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            order = ["python", "go"] if index % 2 == 0 else ["go", "python"]
            row = {"id": case["id"], "facts": len(case["facts"]), "order": order}
            for language in order:
                print(f"Medindo {case['id']} / {language}...", flush=True)
                if language == "python":
                    command = [
                        sys.executable,
                        "-m",
                        "benchmarks.medicao.python_worker",
                        "--input",
                        str(path),
                        "--warmups",
                        str(args.warmups),
                        "--repetitions",
                        str(args.repetitions),
                    ]
                else:
                    command = [
                        str(binary),
                        "-input",
                        str(path),
                        "-catalogs",
                        str(PROCESSING / "src/argus_processing/catalogs"),
                        "-warmups",
                        str(args.warmups),
                        "-repetitions",
                        str(args.repetitions),
                    ]
                row[language] = medir_processo(command, cpu, args.repetitions)
            result["workloads"].append(row)
    if hashes() != before:
        raise RuntimeError("Código ou dados mudaram durante a rodada; descarte a medição")
    return result


def main() -> None:
    """Verifica paridade e executa a medição solicitada pelo Makefile."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go")
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=50)
    parser.add_argument("--label", default="rodada local exploratória")
    parser.add_argument(
        "--output-dir", type=Path, default=REPO / "artefatos/benchmark/resultados-local"
    )
    args = parser.parse_args()
    if args.warmups < 3 or args.repetitions < 20:
        parser.error("Use ao menos 3 aquecimentos e 20 repetições")
    result = executar(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "resultados.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Dados brutos salvos em {args.output_dir / 'resultados.json'}")
    print("Documentação: artefatos/benchmark/benchmark-python-vs-golang.md")


if __name__ == "__main__":
    main()
