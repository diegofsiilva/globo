"""Leitura, projeção e comparação do contrato portátil do benchmark."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
from typing import Any

from argus_processing.catalog import Catalog
from argus_processing.detector import detect
from argus_processing.domain import Anomaly, Baseline, Fact, SourceQuality
from argus_processing.quality import evaluate_quality
from argus_processing.rules import build_candidates, evaluate_candidates


def data(value: str | None) -> dt.datetime | None:
    """Preserva o fuso explícito e a ausência de horário."""
    return dt.datetime.fromisoformat(value) if value is not None else None


def ler_fatos(rows: list[dict]) -> tuple[Fact, ...]:
    """Reconstrói os fatos sem mudar sua ordem."""
    return tuple(
        Fact(
            **{
                **row,
                **{k: data(row[k]) for k in ("event_start", "event_end", "available_at")},
            }
        )
        for row in rows
    )


def ler_baselines(rows: list[dict]) -> dict[tuple, Baseline]:
    """Reconstrói as chaves circadianas e o estado inicial."""
    return {
        tuple(row["key"]): Baseline(
            **{**row["value"], "last_event_at": data(row["value"]["last_event_at"])}
        )
        for row in rows
    }


def projetar_anomalia(item: Anomaly) -> dict:
    """Troca o fato embutido por sua chave portátil."""
    result = dataclasses.asdict(item)
    result["fact_key"] = result.pop("fact")["fact_key"]
    return result


def _projetar_evidencias(rows: list | tuple) -> None:
    """Preserva a versão de cada fato citado como evidência."""
    for row in rows:
        fact = row.pop("fact")
        row["fact_key"] = fact["fact_key"] if fact else None
        row["version_lsn"] = fact["version_lsn"] if fact else None


def projetar_candidato(item: Any) -> dict:
    """Exporta candidato sem repetir o conteúdo dos fatos."""
    result = dataclasses.asdict(item)
    subject = result.pop("subject")
    result["subject_fact_key"] = subject["fact_key"] if subject else None
    result["supporting_fact_keys"] = [f["fact_key"] for f in result.pop("supporting")]
    _projetar_evidencias(result["contrary"])
    return result


def projetar_hipotese(item: Any) -> dict:
    """Exporta hipótese completa, incluindo score, chaves e evidências."""
    result = dataclasses.asdict(item)
    _projetar_evidencias(result["evidence"])
    return result


def json_pronto(value: Any) -> Any:
    """Converte datas em ISO 8601 e tuplas em listas JSON."""
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            default=lambda item: (
                item.isoformat() if isinstance(item, dt.datetime) else str(item)
            ),
        )
    )


def resultado_regras(facts, anomalies, quality, catalog: Catalog) -> dict:
    """Executa as regras reais; nunca lê saídas congeladas para calculá-las."""
    candidates = build_candidates(anomalies, facts, quality, catalog)
    hypotheses, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, anomalies, quality, catalog
    )
    return {
        "candidates": [projetar_candidato(c) for c in candidates],
        "hypotheses": [projetar_hipotese(h) for h in hypotheses],
        "candidates_prefiltered": prefiltered,
        "candidates_evaluated": evaluated,
        "candidates_truncated": truncated,
    }


def executar_regras(case: dict, catalog: Catalog) -> dict:
    """Calcula a saída completa de um caso de regras serializado."""
    facts = ler_fatos(case["facts"])
    by_key = {f.fact_key: f for f in facts}
    anomalies = tuple(
        Anomaly(
            **{k: v for k, v in row.items() if k != "fact_key"},
            fact=by_key[row["fact_key"]],
        )
        for row in case["anomalies"]
    )
    quality = tuple(
        SourceQuality(**{**row, "last_observation_at": data(row["last_observation_at"])})
        for row in case["quality"]
    )
    return json_pronto(resultado_regras(facts, anomalies, quality, catalog))


def executar_ciclo(case: dict, catalog: Catalog) -> dict:
    """Calcula qualidade, detector, regras e score sem banco ou relógio real."""
    facts = ler_fatos(case["facts"])
    quality = evaluate_quality(
        facts,
        catalog,
        window_start=data(case["window_start"]),
        window_end=data(case["window_end"]),
        simulator_end=data(case["simulator_end"]),
    )
    anomalies, updates = detect(facts, ler_baselines(case["baselines"]), catalog)
    return json_pronto(
        {
            "quality": [dataclasses.asdict(q) for q in quality],
            "anomalies": [projetar_anomalia(a) for a in anomalies],
            "baseline_updates": [
                {"key": list(k), "value": dataclasses.asdict(v)}
                for k, v in sorted(updates.items())
            ],
            **resultado_regras(facts, anomalies, quality, catalog),
        }
    )


def contagens(case: dict, output: dict) -> dict:
    """Resume as contagens congeladas das cargas maiores."""
    return {
        "facts": len(case["facts"]),
        "anomalies": len(output["anomalies"]),
        **{
            k: output[k]
            for k in (
                "candidates_prefiltered",
                "candidates_evaluated",
                "candidates_truncated",
            )
        },
        "hypotheses": len(output["hypotheses"]),
        **{
            status: sum(h["evaluation_status"] == status for h in output["hypotheses"])
            for status in ("generated", "insufficient_evidence", "discarded")
        },
    }


def comparar(actual: Any, expected: Any, path: str = "resultado") -> None:
    """Exige estrutura e ordem iguais, com tolerância apenas em valores float."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise AssertionError(f"{path}: chaves divergentes")
        for key in expected:
            comparar(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise AssertionError(f"{path}: tamanho/tipo divergente")
        for index, (left, right) in enumerate(zip(actual, expected, strict=True)):
            comparar(left, right, f"{path}[{index}]")
    elif isinstance(expected, float):
        if (
            isinstance(actual, bool)
            or not isinstance(actual, (int, float))
            or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12)
        ):
            raise AssertionError(f"{path}: {actual!r} != {expected!r}")
    elif actual != expected or (isinstance(expected, bool) != isinstance(actual, bool)):
        raise AssertionError(f"{path}: {actual!r} != {expected!r}")
