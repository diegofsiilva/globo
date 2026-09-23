"""Prepara e envia um lote CDC com incidente e controle para testar hipóteses.

O relógio vem de ``sim.now()``. O arquivo JSON deve ficar fora do repositório.
O envio é explícito e nunca é repetido automaticamente: a resposta HTTP confirma
apenas a entrada na fila, não a conclusão do processamento.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

QUARTER = dt.timedelta(minutes=15)
BRT = ZoneInfo("America/Sao_Paulo")
SOURCES = ("prometheus", "apollo")
COHORTS = ("incident", "control")


def generate_batch(sim_now: dt.datetime, batch_id: str) -> dict:
    """Gera 12 amostras circadianas e uma atual para cada uma das quatro séries.

    Args:
        sim_now (datetime): Presente virtual do laboratório, com fuso horário.
        batch_id (str): Identificador exclusivo desta tentativa.

    Returns:
        dict: Corpo aceito por ``POST /v1/changes``.

    Raises:
        ValueError: Se o horário ou identificador não servir para o lote.
    """
    if sim_now.tzinfo is None or sim_now.utcoffset() is None:
        raise ValueError("sim_now precisa conter fuso horário")
    if not re.fullmatch(r"lab-hyp-[a-z0-9-]+", batch_id):
        raise ValueError("batch_id deve começar com lab-hyp- e usar letras minúsculas")

    # Apollo pode levar cinco minutos para ficar visível; dez deixam folga.
    eligible = sim_now.astimezone(dt.UTC) - dt.timedelta(minutes=10)
    spike = dt.datetime.fromtimestamp(int(eligible.timestamp()) // 900 * 900, dt.UTC)
    spike_brt = spike.astimezone(BRT)
    baseline_times = [
        (spike_brt - dt.timedelta(days=days))
        .replace(minute=minute, second=0, microsecond=0)
        .astimezone(dt.UTC)
        for days in (3, 2, 1)
        for minute in (0, 15, 30, 45)
    ]

    captured_at = sim_now.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")
    changes = []
    for cohort in COHORTS:
        for source in SOURCES:
            for index, event_at in enumerate([*baseline_times, spike]):
                pk = {
                    "bts": int(event_at.timestamp() * 1000),
                    "source": source,
                    "entity": f"{batch_id}-{cohort}",
                    "metric": "error_rate_pct",
                }
                value = (
                    (15.0 if cohort == "incident" else 1.0)
                    if index == 12
                    else (0.9, 1.0, 1.1)[index % 3]
                )
                changes.append(
                    {
                        "source_table": "signal_bucket",
                        "op": "i",
                        "pk": pk,
                        # O ETL reconstrói o fato de `after`, portanto ela
                        # precisa conter também a identidade da linha.
                        "after": {**pk, "value": value},
                        "captured_at": captured_at,
                    }
                )
    batch = {"changes": changes}
    validate_batch(batch)
    return batch


def validate_batch(batch: dict) -> None:
    """Recusa lote incompleto ou com chave duplicada antes do envio.

    Args:
        batch (dict): Corpo JSON gerado ou lido do disco.

    Raises:
        ValueError: Se o lote não cumprir o contrato do experimento.
    """
    changes = batch.get("changes")
    if not isinstance(changes, list) or len(changes) != 52:
        raise ValueError("o lote precisa conter exatamente 52 mudanças")
    keys = set()
    series: dict[tuple[str, str], list[dict]] = {}
    for change in changes:
        pk = change.get("pk", {})
        if change.get("source_table") != "signal_bucket" or change.get("op") != "i":
            raise ValueError("somente inserts de signal_bucket são aceitos")
        if change.get("after") != {**pk, "value": change.get("after", {}).get("value")}:
            raise ValueError("after precisa conter a PK completa e value")
        key = tuple(pk.get(part) for part in ("bts", "source", "entity", "metric"))
        if None in key or key in keys:
            raise ValueError("chave primária ausente ou duplicada")
        keys.add(key)
        if pk["source"] not in SOURCES or pk["metric"] != "error_rate_pct":
            raise ValueError("fonte ou métrica inesperada")
        series.setdefault((pk["entity"], pk["source"]), []).append(change)
    if len(series) != 4 or any(len(items) != 13 for items in series.values()):
        raise ValueError("o lote precisa de quatro séries com 13 amostras")
    for (entity, _), items in series.items():
        ordered = sorted(items, key=lambda item: item["pk"]["bts"])
        expected = 15.0 if entity.endswith("-incident") else 1.0
        if not entity.endswith(("-incident", "-control")):
            raise ValueError("entidade fora dos grupos do experimento")
        if ordered[-1]["after"]["value"] != expected:
            raise ValueError("valor final não corresponde ao grupo")


def _database():
    """Abre uma conexão de leitura operacional com o banco configurado."""
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL é necessária para consultar o banco")
    return psycopg.connect(url, connect_timeout=10)


def _prepare(args: argparse.Namespace) -> None:
    """Grava um payload auditável sem tocar na API de ingestão."""
    manifest_path = args.output.with_suffix(".manifest.json")
    if args.output.exists() or manifest_path.exists():
        raise ValueError(f"arquivo ou manifesto já existe: {args.output}")
    if args.sim_now:
        sim_now = dt.datetime.fromisoformat(args.sim_now)
        preflight_lsn = None
    else:
        with _database() as connection:
            sim_now, preflight_lsn = connection.execute(
                "SELECT sim.now(), COALESCE(max(lsn), 0) FROM bronze.change_log"
            ).fetchone()
    batch_id = args.batch_id or f"lab-hyp-{uuid.uuid4().hex[:12]}"
    batch = generate_batch(sim_now, batch_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_path.write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "sim_now": sim_now.isoformat(),
                "preflight_lsn": preflight_lsn,
                "incident_entity": f"{batch_id}-incident",
                "control_entity": f"{batch_id}-control",
                "change_count": 52,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"lote={batch_id} mudanças=52 relógio={sim_now.isoformat()}")
    print(f"arquivo={args.output} manifesto={manifest_path}")
    print("revise o arquivo antes de executar o envio")


def _send(args: argparse.Namespace) -> None:
    """Envia uma vez o payload salvo e grava o recibo de aceitação HTTP."""
    batch = json.loads(args.input.read_text(encoding="utf-8"))
    validate_batch(batch)
    receipt = args.input.with_suffix(".sent.json")
    if receipt.exists():
        raise ValueError(f"recibo já existe; não reenvie o mesmo lote: {receipt}")
    url = os.environ.get("ARGUS_CHANGES_URL")
    token = os.environ.get("ARGUS_INGEST_TOKEN")
    if not url or not token:
        raise ValueError("ARGUS_CHANGES_URL e ARGUS_INGEST_TOKEN são necessários")
    request = urllib.request.Request(
        url,
        data=json.dumps(batch, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = response.status
            response_body = response.read(1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise ValueError(f"API recusou o lote: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(
            "envio incerto; verifique Bronze antes de tentar novamente"
        ) from exc
    if not 200 <= status < 300:
        raise ValueError(f"API respondeu HTTP {status}; verifique Bronze")
    receipt.write_text(
        json.dumps(
            {"http_status": status, "response": response_body},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"HTTP {status}; 52 mudanças aceitas pela fila; recibo={receipt}")


def _verify(args: argparse.Namespace) -> bool:
    """Consulta as camadas e exige evidência do lote na hipótese gerada."""
    batch = json.loads(args.input.read_text(encoding="utf-8"))
    validate_batch(batch)
    manifest = json.loads(
        args.input.with_suffix(".manifest.json").read_text(encoding="utf-8")
    )
    start_lsn = manifest["preflight_lsn"]
    if start_lsn is None:
        raise ValueError("manifesto de ensaio local não possui LSN inicial")
    incident = manifest["incident_entity"]
    control = manifest["control_entity"]
    with _database() as connection:
        rows = connection.execute(
            """
            SELECT lsn, after->>'entity' AS entity
              FROM bronze.change_log
             WHERE lsn > %s AND source_table = 'signal_bucket'
               AND after->>'entity' = ANY(%s)
             ORDER BY lsn
            """,
            (start_lsn, [incident, control]),
        ).fetchall()
        lsns = [row[0] for row in rows]
        max_lsn = max(lsns, default=0)
        silver = 0
        watermark = 0
        checkpoint = None
        run = None
        anomalies = {incident: 0, control: 0}
        hypotheses = []
        if lsns:
            silver = connection.execute(
                "SELECT count(*) FROM silver.analysis_fact_version WHERE version_lsn = ANY(%s)",
                (lsns,),
            ).fetchone()[0]
            watermark = connection.execute(
                "SELECT lsn_processado FROM etl.watermark_bronze_silver WHERE id = 1"
            ).fetchone()[0]
            checkpoint = connection.execute(
                """SELECT checkpoint_id, source_lsn FROM etl.gold_checkpoint
                   WHERE source_lsn >= %s ORDER BY checkpoint_id LIMIT 1""",
                (max_lsn,),
            ).fetchone()
            run = connection.execute(
                """SELECT r.run_id, r.status, r.input_lsn, s.truncated
                     FROM detect.run r
                     JOIN detect.run_input_fact f ON f.run_id = r.run_id
                LEFT JOIN gold.hypothesis_run_stats s ON s.run_id = r.run_id
                    WHERE f.version_lsn = ANY(%s)
                    ORDER BY r.run_id DESC LIMIT 1""",
                (lsns,),
            ).fetchone()
            if run and run[1] == "completed":
                anomalies.update(
                    connection.execute(
                        """SELECT entity, count(*) FROM detect.anomaly
                            WHERE run_id = %s AND entity = ANY(%s) GROUP BY entity""",
                        (run[0], [incident, control]),
                    ).fetchall()
                )
                hypotheses = connection.execute(
                    """SELECT DISTINCT h.hypothesis_id, h.family, h.evaluation_status,
                                      h.score, h.coverage, e.entity
                         FROM gold.hypothesis h
                         JOIN gold.hypothesis_evidence e
                           ON e.hypothesis_id = h.hypothesis_id
                        WHERE h.run_id = %s AND e.version_lsn = ANY(%s)
                          AND e.entity = ANY(%s)
                        ORDER BY h.hypothesis_id, e.entity""",
                    (run[0], lsns, [incident, control]),
                ).fetchall()
    incident_hypotheses = [
        row
        for row in hypotheses
        if row[1] == "backend_internal" and row[2] == "generated" and row[5] == incident
    ]
    evidence_sources = set()
    if incident_hypotheses:
        with _database() as connection:
            evidence_sources = {
                row[0]
                for row in connection.execute(
                    """SELECT DISTINCT source FROM gold.hypothesis_evidence
                        WHERE hypothesis_id = ANY(%s) AND version_lsn = ANY(%s)
                          AND entity = %s AND polarity = 'favorable'
                          AND source IS NOT NULL""",
                    ([row[0] for row in incident_hypotheses], lsns, incident),
                ).fetchall()
            }
    success = (
        len(rows) == 52
        and silver == 52
        and watermark >= max_lsn
        and checkpoint is not None
        and run is not None
        and run[1] == "completed"
        and run[3] is False
        and anomalies[incident] >= 2
        and anomalies[control] == 0
        and bool(incident_hypotheses)
        and all(row[3] >= 40 and row[4] >= 0.5 for row in incident_hypotheses)
        and set(SOURCES) <= evidence_sources
        and not any(row[5] == control for row in hypotheses)
    )
    report = {
        "batch_id": manifest["batch_id"],
        "bronze": len(rows),
        "max_lsn": max_lsn,
        "silver": silver,
        "bronze_silver_watermark": watermark,
        "checkpoint": checkpoint,
        "run": run,
        "anomalies": anomalies,
        "hypotheses": hypotheses,
        "evidence_sources": sorted(evidence_sources),
        "success": success,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return success


def main() -> int:
    """Executa a preparação ou o envio conforme o subcomando."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    prepare = subcommands.add_parser("prepare", help="gera arquivo sem enviar")
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--batch-id")
    prepare.add_argument("--sim-now", help="horário virtual ISO para ensaio local")
    send = subcommands.add_parser("send", help="envia arquivo uma única vez")
    send.add_argument("--input", type=Path, required=True)
    verify = subcommands.add_parser("verify", help="consulta o progresso e as evidências")
    verify.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            _prepare(args)
        elif args.command == "send":
            _send(args)
        elif not _verify(args):
            return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, f"erro: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
