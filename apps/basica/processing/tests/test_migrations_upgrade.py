"""Instalacao limpa e upgrade real do contrato de analise."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


def test_instalacao_da_suite_aplica_todas_as_migrations(database_url):
    with psycopg.connect(database_url) as conn:
        versions = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()

    esperadas = [path.stem for path in sorted(MIGRATIONS.glob("*.sql"))]
    assert [version for (version,) in versions] == esperadas


def test_upgrade_017_para_022_em_banco_existente(database_url):
    params = conninfo_to_dict(database_url)
    database = f"argus_upgrade_{os.getpid()}"
    admin_params = {**params, "dbname": "postgres"}
    target_params = {**params, "dbname": database}

    with psycopg.connect(**admin_params, autocommit=True) as admin:
        admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                sql.Identifier(database)
            )
        )
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        with psycopg.connect(**target_params, autocommit=True) as conn:
            paths = sorted(MIGRATIONS.glob("*.sql"))
            for path in paths[:17]:
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
            assert conn.execute("SELECT to_regclass('detect.work_claim')").fetchone()[0]

            for path in paths[17:22]:
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))

            expected = (
                "silver.analysis_fact_version",
                "detect.analysis_cursor",
                "gold.source_quality",
                "gold.hypothesis",
                "gold.v_hypothesis",
            )
            for relation in expected:
                assert conn.execute("SELECT to_regclass(%s)", (relation,)).fetchone()[0]
    finally:
        with psycopg.connect(**admin_params, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database)
                )
            )
