"""Operacoes controladas de publicacao do manifesto de analise."""

from __future__ import annotations

import argparse
import json
import os

from argus_common import Database

from argus_processing.analysis_repository import promote_manifest
from argus_processing.catalog import Catalog

FAMILIES = {
    "deploy_regression",
    "backend_internal",
    "playback_authorization",
    "cdn_degradation",
    "origin_encoding",
    "regional_or_isp",
    "waf_block",
    "player_or_device",
    "qoe_without_error",
    "expected_live_peak",
    "source_data_delay",
}


def evaluate(db: Database, catalog: Catalog, args: argparse.Namespace) -> dict:
    """Reune os criterios de promocao do manifesto atual.

    O motor sobe em modo sombra: as views de hipotese ficam vazias ate um evento
    `published` (AGENTS.md, regra 6). Esta funcao junta o que decide se esse
    evento deve ser emitido -- execucoes falhas, divergencia de digest de
    entrada, truncamento, cobertura das familias e as medidas que so um humano
    pode confirmar (precisao, latencia da API, SLA de checkpoint, suite).

    Args:
        db (Database): Conexao com o banco.
        catalog (Catalog): Manifesto avaliado.
        args (argparse.Namespace): As medidas informadas na linha de comando.

    Returns:
        dict: As metricas apuradas mais `failures`, a lista do que reprovou.
            Lista vazia significa apto a promover.
    """
    row = db.fetch_one(
        """
        SELECT count(*) FILTER (WHERE r.status = 'failed') AS failed,
               count(*) FILTER (
                 WHERE r.error_message LIKE 'input_digest_mismatch:%%'
               ) AS digest_divergence,
               count(*) FILTER (WHERE s.truncated) AS truncated,
               count(*) FILTER (WHERE r.status = 'completed') AS completed
          FROM detect.run r
          LEFT JOIN gold.hypothesis_run_stats s ON s.run_id = r.run_id
         WHERE r.manifest_hash = %s
        """,
        (catalog.manifest_hash,),
    )
    family_rows = db.fetch_all(
        """
        SELECT DISTINCT h.family
          FROM gold.hypothesis h
          JOIN detect.run r ON r.run_id = h.run_id
         WHERE r.manifest_hash = %s AND r.status = 'completed'
        """,
        (catalog.manifest_hash,),
    )
    observed_families = {item["family"] for item in family_rows}
    violations = db.fetch_one(
        """
        SELECT count(*) AS temporal_violations
          FROM gold.hypothesis_evidence e
          JOIN gold.hypothesis h ON h.hypothesis_id = e.hypothesis_id
          JOIN detect.run r ON r.run_id = h.run_id
         WHERE r.manifest_hash = %s
           AND e.available_at > r.sim_now
        """,
        (catalog.manifest_hash,),
    )
    metrics = {
        "failed_runs": row["failed"],
        "digest_divergence": row["digest_divergence"],
        "temporal_violations": violations["temporal_violations"],
        "truncated_runs": row["truncated"],
        "completed_runs": row["completed"],
        "families_observed": sorted(observed_families),
        "precision_at_5": args.precision_at_5,
        "api_p95_ms": args.api_p95_ms,
        "api_max_ms": args.api_max_ms,
        "checkpoint_sla_ok": args.checkpoint_sla_ok,
        "suite_ok": args.suite_ok,
    }
    failures = []
    if row["failed"]:
        failures.append("ha runs com falha")
    if row["truncated"]:
        failures.append("ha runs truncados")
    if row["digest_divergence"]:
        failures.append("ha retry com digest divergente")
    if violations["temporal_violations"]:
        failures.append("ha evidencia posterior ao sim_now")
    if not row["completed"]:
        failures.append("nenhum run concluido")
    if observed_families != FAMILIES:
        failures.append(f"familias sem resultado: {sorted(FAMILIES - observed_families)}")
    if args.precision_at_5 < 0.60:
        failures.append("precision@5 abaixo de 0.60")
    if args.api_p95_ms > 3000 or args.api_max_ms > 5000:
        failures.append("API fora do SLO")
    if not args.checkpoint_sla_ok:
        failures.append("processamento nao acompanha checkpoints")
    if not args.suite_ok:
        failures.append("suite e cenarios das 11 familias nao confirmados")
    metrics["failures"] = failures
    return metrics


def parser() -> argparse.ArgumentParser:
    """Monta a linha de comando do `analysisctl`.

    Returns:
        argparse.ArgumentParser: Parser com `evaluate-and-promote`, `withdraw` e
            `manifest`.
    """
    root = argparse.ArgumentParser(prog="analysisctl")
    sub = root.add_subparsers(dest="command", required=True)
    promote = sub.add_parser("evaluate-and-promote")
    promote.add_argument("--precision-at-5", type=float, required=True)
    promote.add_argument("--api-p95-ms", type=float, required=True)
    promote.add_argument("--api-max-ms", type=float, required=True)
    promote.add_argument("--checkpoint-sla-ok", action="store_true")
    promote.add_argument("--suite-ok", action="store_true")
    sub.add_parser("withdraw")
    sub.add_parser("manifest")
    return root


def main() -> int:
    """Ponto de entrada da CLI de operacao do motor.

    Returns:
        int: 0 em sucesso. `evaluate-and-promote` devolve diferente de zero
            quando algum criterio reprova, e nesse caso NAO promove -- e o que
            permite encadear o comando num passo de verificacao.
    """
    args = parser().parse_args()
    catalog = Catalog(os.getenv("IMAGE_TAG", "local"))
    if args.command == "manifest":
        print(json.dumps({"manifest_hash": catalog.manifest_hash}, indent=2))
        return 0
    db = Database.from_env(min_size=1, max_size=2, application_name="analysisctl")
    try:
        if args.command == "withdraw":
            promote_manifest(
                db, catalog.manifest_hash, {"reason": "operator"}, withdraw=True
            )
            return 0
        metrics = evaluate(db, catalog, args)
        print(json.dumps(metrics, indent=2, default=str))
        if metrics["failures"]:
            return 2
        promote_manifest(db, catalog.manifest_hash, metrics)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
