"""Controla a rodada local Python × Go e grava amostras e relatório auditáveis."""

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


def relatorio(result: dict) -> str:
    """Explica escopo e limitações junto dos números de todas as etapas."""
    host, protocol = result["environment"], result["protocol"]
    lines = [
        "# Benchmark local exploratório — Python × Go",
        "",
        f"Rodada: **{result['label']}**. Paridade aprovada antes da medição em "
        "49 cenários de regras, um ciclo base e quatro cargas (54 saídas completas).",
        "",
        "## Ambiente e protocolo",
        "",
        f"- Sistema: {host['os']} {host['os_release']} ({host['os_version']}), "
        f"{host['architecture']}.",
        f"- CPU: {host['cpu']}; {host['logical_cpus']} CPUs lógicas; "
        f"memória física: {host['physical_memory_bytes'] / 2**30:.2f} GiB.",
        f"- Ambos os filhos restritos à CPU lógica {protocol['cpu_affinity']}; "
        "um processo medido por vez; Go com GOMAXPROCS=1.",
        f"- {protocol['warmups']} aquecimentos e {protocol['repetitions']} amostras "
        "por etapa e por linguagem. p95: nearest rank.",
        "- Ordem das linguagens alternada entre cargas. Etapas na ordem: "
        "qualidade, detector, candidatos, score, total.",
        "- JSON, catálogos e entradas tipadas carregados antes do cronômetro. "
        "Compilação, comparação, serialização e I/O fora dos tempos.",
        "- GC padrão habilitado: CPython; Go GOGC=100 e GOMEMLIMIT=off. "
        "Sem limite adicional de memória.",
        "- Uma execução por perfil em uma máquina de desenvolvimento; frequência "
        "da CPU, energia e processos externos não foram controlados.",
        "",
        "## Cálculo completo",
        "",
        "A razão é mediana Python / mediana Go; maior que 1 favorece Go. "
        "O total é cronometrado separadamente e não é a soma das medianas.",
        "",
        "| Carga | Fatos | Python mediana (ms) | Python p95 (ms) | Go mediana (ms) | "
        "Go p95 (ms) | Razão | RSS Python (MiB) | RSS Go (MiB) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in result["workloads"]:
        py, go = row["python"], row["go"]
        p, g = py["summary"]["total"], go["summary"]["total"]
        lines.append(
            f"| {row['id']} | {row['facts']} | {p['median_ms']:.4f} | "
            f"{p['p95_ms']:.4f} | {g['median_ms']:.4f} | {g['p95_ms']:.4f} | "
            f"{p['median_ms'] / g['median_ms']:.2f}× | "
            f"{py['peak_rss_bytes'] / 2**20:.2f} | {go['peak_rss_bytes'] / 2**20:.2f} |"
        )
    lines += ["", "## Por etapa", ""]
    for row in result["workloads"]:
        lines += [
            f"### {row['id']}",
            "",
            f"Runtimes: {row['python']['runtime']} e {row['go']['runtime']}.",
            f"Relógios: {row['python']['clock']} (Python), {row['go']['clock']} (Go). "
            f"Resoluções declaradas: {row['python']['clock_resolution_ns']:g} ns / "
            f"{row['go']['clock_resolution_ns']:g} ns. "
            "Overhead do cronômetro não subtraído.",
            "",
            "| Etapa | Python mediana (ms) | Python p95 (ms) | "
            "Go mediana (ms) | Go p95 (ms) | Razão |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for stage in STAGES:
            p, g = row["python"]["summary"][stage], row["go"]["summary"][stage]
            lines.append(
                f"| {stage} | {p['median_ms']:.4f} | {p['p95_ms']:.4f} | "
                f"{g['median_ms']:.4f} | {g['p95_ms']:.4f} | "
                f"{p['median_ms'] / g['median_ms']:.2f}× |"
            )
        lines.append("")
    lines += [
        "## Interpretação e limites",
        "",
        "- A rodada mede estas implementações e estas cargas sintéticas. Não isola "
        "o efeito da linguagem de diferenças de implementação e runtime.",
        "- O pico de RSS inclui inicialização, dados, runtime, aquecimentos e todas "
        "as etapas do processo. Não representa apenas alocações do motor nem "
        "memória incremental por chamada.",
        "- No Windows foi usado [PeakWorkingSetSize](https://learn.microsoft.com/"
        "en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters); "
        "no Linux, o contador VmHWM do processo.",
        "- Banco, captura, claim/lease, persistência, rede e ETL estão fora. "
        "Estes números não estimam latência ou custo da arquitetura na AWS.",
        "- A equipe ainda não definiu o ganho mínimo para justificar uma migração. "
        "Esta rodada exploratória não aprova uma mudança de produção.",
        "- Uma decisão posterior requer critério prévio, rodadas independentes "
        "e medição do ciclo com banco em ambiente representativo.",
        "",
        "## Evidências",
        "",
        "O arquivo `resultados.json` ao lado contém todas as amostras em ns, "
        "estatísticas, versões, hardware, ordem de execução e hashes SHA-256 dos "
        "dados e do código. Os hashes permitem identificar também código sem commit.",
        "",
    ]
    return "\n".join(lines)


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
    (args.output_dir / "relatorio.md").write_text(relatorio(result), encoding="utf-8")
    print(f"Resultados salvos em {args.output_dir}")


if __name__ == "__main__":
    main()
