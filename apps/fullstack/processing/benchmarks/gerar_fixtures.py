"""Recria os dados sintéticos do benchmark a partir dos cenários Python."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from argus_processing.catalog import Catalog
from argus_processing.domain import Baseline, Fact
from benchmarks.contrato import (
    contagens,
    executar_ciclo,
    json_pronto,
    projetar_anomalia,
    resultado_regras,
)

PROCESSING = Path(__file__).resolve().parents[1]
FIXTURES = PROCESSING / "benchmarks" / "fixtures"
# Origem histórica dos cenários já entregues. Os hashes abaixo identificam o
# conteúdo efetivamente usado, inclusive mudanças ainda não commitadas.
SOURCE_REVISION = "534a9ca"


def _carregar_teste(name: str):
    """Carrega módulo novo em cada geração para reiniciar seus IDs deterministas."""
    spec = importlib.util.spec_from_file_location(
        name, PROCESSING / "tests" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _proveniencia(catalog: Catalog) -> dict:
    """Registra SHA-256 dos arquivos de origem, normalizando CRLF para LF."""
    paths = [
        PROCESSING / "tests" / f"{name}.py" for name in ("test_familias", "test_rules")
    ]
    paths += [
        PROCESSING / "src" / "argus_processing" / f"{name}.py"
        for name in ("catalog", "domain", "quality", "detector", "rules", "scoring")
    ]
    paths += list((PROCESSING / "benchmarks").glob("*.py"))
    return {
        "schema_version": 1,
        "catalog_manifest_hash": catalog.manifest_hash,
        "source_files_sha256": {
            path.relative_to(PROCESSING).as_posix(): hashlib.sha256(
                path.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            for path in sorted(paths)
        },
    }


def gerar_regras(catalog: Catalog) -> dict:
    """Captura as entradas dos testes e também executa suas asserções originais."""
    module = _carregar_teste("test_familias")
    original = module._run
    cases = []
    current_test = ""
    call_index = 0

    def capturar(family, anomalies, facts, extra_quality=()):
        """Congela todas as famílias, mantendo a família foco só como rótulo."""
        nonlocal call_index
        call_index += 1
        sources = {f.source for f in facts} | {a.fact.source for a in anomalies}
        declared = {q.source for q in extra_quality}
        quality = extra_quality + tuple(
            module._quality(source) for source in sorted(sources - declared)
        )
        cases.append(
            {
                "id": f"{current_test}.{call_index:02d}",
                "focus_family": family,
                "facts": [dataclasses.asdict(f) for f in facts],
                "anomalies": [projetar_anomalia(a) for a in anomalies],
                "quality": [dataclasses.asdict(q) for q in quality],
                "expected": resultado_regras(facts, anomalies, quality, catalog),
            }
        )
        return original(family, anomalies, facts, extra_quality)

    module._run = capturar
    try:
        for name, function in list(vars(module).items()):
            if name.startswith("test_") and callable(function):
                current_test, call_index = name, 0
                function()
    finally:
        module._run = original
    return {
        "purpose": "Paridade funcional das onze familias; dados sinteticos extraidos "
        "de testes do repositorio.",
        "source_test": "apps/fullstack/processing/tests/test_familias.py",
        "source_revision": SOURCE_REVISION,
        "cases": cases,
    }


def gerar_ciclo(catalog: Catalog) -> dict:
    """Acrescenta baselines sintéticos ao cenário misto das onze famílias."""
    module = _carregar_teste("test_rules")
    original = module.build_candidates
    captured = {}

    def capturar(anomalies, facts, qualities, test_catalog):
        """Obtém somente entradas; as anomalias manuais servem para semear baselines."""
        captured.update(facts=facts, anomalies=anomalies)
        return original(anomalies, facts, qualities, test_catalog)

    module.build_candidates = capturar
    try:
        module.test_as_onze_familias_formam_candidatos_em_cenarios_positivos()
    finally:
        module.build_candidates = original
    baselines = {}
    for anomaly in captured["anomalies"]:
        fact = anomaly.fact
        policy = catalog.metric(fact.metric)
        typical = (
            1000.0
            if fact.metric == "active_sessions"
            else 10.0
            if "latency" in fact.metric or "jointime" in fact.metric
            else 1.0
        )
        key = (
            fact.source,
            fact.entity,
            fact.metric,
            fact.event_start.astimezone(ZoneInfo("America/Sao_Paulo")).hour,
        )
        baselines[key] = Baseline(
            mean=math.log1p(typical) if policy.transform == "log1p" else typical,
            variance=0.01,
            n=12,
            last_event_at=fact.event_start - dt.timedelta(days=1),
        )
    case = json_pronto(
        {
            "id": "ciclo_misto_v1",
            "facts": [dataclasses.asdict(f) for f in captured["facts"]],
            "baselines": [
                {"key": k, "value": dataclasses.asdict(v)}
                for k, v in sorted(baselines.items())
            ],
            "window_start": module.NOW - dt.timedelta(minutes=1),
            "window_end": module.NOW,
            "simulator_end": module.NOW,
        }
    )
    case["expected"] = executar_ciclo(case, catalog)
    return {
        "purpose": "Entrada sintetica fixa para o calculo qualidade, detector, regras "
        "e score.",
        "source_test": "apps/fullstack/processing/tests/test_rules.py::"
        "test_as_onze_familias_formam_candidatos_em_cenarios_positivos",
        "source_revision": SOURCE_REVISION,
        "case": case,
    }


def gerar_cargas(base: dict, catalog: Catalog) -> dict:
    """Amplia fatos ou anomalias sem usar números aleatórios nem dados do parceiro."""
    workloads = []
    now = dt.datetime.fromisoformat(base["window_end"])
    for dense, size in ((False, 256), (False, 1024), (True, 128), (True, 512)):
        name = f"{'denso' if dense else 'disperso'}_{size}"
        case = {k: v for k, v in base.items() if k not in {"id", "expected"}}
        case.update(id=name, profile="anomalias_densas" if dense else "fatos_sem_desvio")
        case["facts"], case["baselines"] = list(base["facts"]), list(base["baselines"])
        for index in range(size - len(base["facts"])):
            fact = Fact(
                fact_key=f"benchmark-{name}-{index:05d}",
                version_lsn=10000 + index,
                role="subject",
                kind="metric",
                event_start=now,
                event_end=None,
                available_at=now,
                source="newrelic" if dense else "prometheus",
                entity=f"benchmark-{'servico' if dense else 'ruido'}-{index:05d}",
                metric="error_rate_pct" if dense else "cpu_pct",
                dimension_type=None,
                dimension_value=None,
                value=5.0 if dense else 10.0,
                sample_size=1000,
            )
            case["facts"].append(json_pronto(dataclasses.asdict(fact)))
            if dense:
                case["baselines"].append(
                    json_pronto(
                        {
                            "key": [
                                fact.source,
                                fact.entity,
                                fact.metric,
                                now.astimezone(ZoneInfo("America/Sao_Paulo")).hour,
                            ],
                            "value": dataclasses.asdict(
                                Baseline(
                                    mean=1.0,
                                    variance=0.01,
                                    n=12,
                                    last_event_at=now - dt.timedelta(days=1),
                                )
                            ),
                        }
                    )
                )
        case["expected_counts"] = contagens(case, executar_ciclo(case, catalog))
        workloads.append(case)
    return {
        "purpose": "Cargas sinteticas fixas para medir crescimento do calculo; "
        "todas derivadas do ciclo_caso_v1.",
        "workloads": workloads,
    }


def gerar() -> dict[str, dict]:
    """Recria os três documentos sem ler nenhum JSON congelado como entrada."""
    catalog = Catalog()
    provenance = _proveniencia(catalog)
    rules = gerar_regras(catalog)
    cycle = gerar_ciclo(catalog)
    loads = gerar_cargas(cycle["case"], catalog)
    return {
        name: json_pronto({**value, **provenance})
        for name, value in (
            ("regras_casos_v1.json", rules),
            ("ciclo_caso_v1.json", cycle),
            ("cargas_v1.json", loads),
        )
    }


def main() -> None:
    """Gera os arquivos ou verifica divergências sem sobrescrevê-los."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Confere sem escrever")
    parser.add_argument("--output-dir", type=Path, default=FIXTURES)
    args = parser.parse_args()
    documents = gerar()
    divergent = []
    for name, document in documents.items():
        path = args.output_dir / name
        content = (
            json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                divergent.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if divergent:
        raise SystemExit("Fixtures divergentes: " + ", ".join(divergent))
    print("3 JSONs " + ("reproduzidos sem divergências." if args.check else "gerados."))


if __name__ == "__main__":
    main()
