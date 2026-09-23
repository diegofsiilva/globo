"""Operacoes controladas de publicacao do manifesto de analise."""

from __future__ import annotations

import argparse
import json
import os

from argus_common import Database
from psycopg.types.json import Jsonb

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


def preview_hypothesis(
    db: Database, hypothesis_id: int, *, withdraw: bool = False
) -> bool:
    """Mostra só uma hipótese no lab ou retira essa visualização.

    Esta ação é registrada como ``preview`` e não afirma que o manifesto
    passou no portão de promoção. O evento ``withdrawn`` restaura o modo
    sombra para esse manifesto.

    Args:
        db (Database): Conexão com o banco.
        hypothesis_id (int): Hipótese gerada e concluída.
        withdraw (bool): Retira uma prévia ativa desse mesmo identificador.

    Returns:
        bool: ``True`` quando o evento foi registrado.
    """
    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT r.manifest_hash, r.status, h.evaluation_status,
                   COALESCE(s.truncated, true), h.effect_start, r.sim_now
              FROM gold.hypothesis h
              JOIN detect.run r ON r.run_id = h.run_id
              LEFT JOIN gold.hypothesis_run_stats s ON s.run_id = r.run_id
             WHERE h.hypothesis_id = %s
            """,
            (hypothesis_id,),
        ).fetchone()
        if row is None:
            return False
        manifest_hash, run_status, evaluation_status, truncated, effect_start, sim_now = (
            row
        )
        latest = conn.execute(
            """
            SELECT action, gate_metrics->>'hypothesis_id'
              FROM gold.manifest_publication_event
             WHERE manifest_hash = %s
             ORDER BY publication_event_id DESC LIMIT 1
            """,
            (manifest_hash,),
        ).fetchone()
        if withdraw:
            if latest != ("preview", str(hypothesis_id)):
                return False
            action = "withdrawn"
        else:
            if (
                run_status != "completed"
                or evaluation_status != "generated"
                or truncated
                or effect_start > sim_now
                or latest is not None
                and latest[0] == "published"
            ):
                return False
            action = "preview"
        conn.execute(
            """
            INSERT INTO gold.manifest_publication_event
              (manifest_hash, action, gate_metrics)
            VALUES (%s, %s, %s)
            """,
            (
                manifest_hash,
                action,
                Jsonb(
                    {"hypothesis_id": hypothesis_id, "reason": "lab_visual_inspection"}
                ),
            ),
        )
    return True


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
    preview = sub.add_parser("preview")
    preview.add_argument("--hypothesis-id", type=int, required=True)
    withdraw_preview = sub.add_parser("withdraw-preview")
    withdraw_preview.add_argument("--hypothesis-id", type=int, required=True)
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
        if args.command in ("preview", "withdraw-preview"):
            success = preview_hypothesis(
                db, args.hypothesis_id, withdraw=args.command == "withdraw-preview"
            )
            print(json.dumps({"hypothesis_id": args.hypothesis_id, "success": success}))
            return 0 if success else 2
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
