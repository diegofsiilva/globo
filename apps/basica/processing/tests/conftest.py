"""Fixtures dos testes do processamento (ETL incremental).

Testes de banco rodam contra um PostgreSQL DE VERDADE, e nao contra um duble --
mesmo motivo do worker de ingestao (ver `worker/tests/conftest.py`): a parte
dificil da ETL incremental mora no SQL (o `SELECT ... FOR UPDATE`, o avanco
atomico do watermark, o `EXCEPTION WHEN OTHERS`). Suba o banco com
`make db-local`. Sem ele, os testes de banco sao PULADOS.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
TOOLS = Path(__file__).resolve().parents[2] / "tools"


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL do PostgreSQL de teste, ou pula a suite de banco."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL nao definida (rode `make db-local`)")

    import psycopg

    try:
        with psycopg.connect(url, connect_timeout=2):
            pass
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL de teste indisponivel (rode `make db-local`)")
    return url


@pytest.fixture(scope="session")
def _migrated(database_url):
    """Aplica as migrations uma vez por sessao de teste."""
    resultado = subprocess.run(
        [sys.executable, str(TOOLS / "migrate.py"), "aplicar"],
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        pytest.fail(f"migrations falharam:\n{resultado.stdout}\n{resultado.stderr}")
    return database_url


@pytest.fixture
def db(_migrated):
    """Pool de conexao, com bronze/silver/gold/etl limpos antes de cada teste.

    Os dois watermarks NAO sao truncados -- sao linha unica travada por CHECK
    -- e sim resetados por UPDATE para o estado semeado pela migration 015.
    """
    from argus_common import Database

    banco = Database(_migrated, min_size=1, max_size=4, application_name="teste")
    with banco.connection() as conn:
        conn.execute(
            """
            TRUNCATE bronze.change_log, bronze.event, bronze.signal_bucket,
                     bronze.signal_point, bronze.live_event, bronze.incidents,
                     bronze.incident_label,
                     silver.signal_point, silver.signal_bucket, silver.session_event,
                     gold.feature_bucket, gold.live_event_window, gold.incident_window,
                     etl.execucoes
              RESTART IDENTITY CASCADE
            """
        )
        conn.execute(
            "UPDATE etl.watermark_bronze_silver"
            "   SET lsn_processado = 0, execucao_id = NULL"
            " WHERE id = 1"
        )
        conn.execute(
            "UPDATE etl.watermark_silver_gold"
            "   SET available_at_processado = timestamptz '2026-07-01 00:00:00+00',"
            "       margem_seguranca = interval '2 hours', execucao_id = NULL"
            " WHERE id = 1"
        )
        conn.execute("SELECT sim.set_clock(timestamptz '2026-07-12 12:00:00+00', 1)")
    yield banco
    banco.close()


@pytest.fixture
def checkpoint(db):
    """Publica uma versao Gold pronta para os testes de coordenacao."""
    from argus_processing import etl

    resultado = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)
    assert resultado["status"] == "sucesso"
    publicado = db.fetch_one(
        """
        SELECT checkpoint_id, ready_through, source_lsn
          FROM etl.gold_checkpoint
         ORDER BY checkpoint_id DESC
         LIMIT 1
        """
    )
    assert publicado is not None
    return publicado


@pytest.fixture
def inserir_change():
    """Devolve uma funcao que insere uma linha em `bronze.change_log`.

    Fixture (em vez de import direto do teste) porque `worker/tests` -- que
    esta suite de `processing` segue como convencao -- nao tem `__init__.py`,
    entao `tests/` nao e um pacote e um import relativo entre arquivos de
    teste nao resolveria.
    """
    import json

    def _inserir(
        conn, tabela: str, after: dict, pk: dict | None = None, op: str = "i"
    ) -> int:
        """Insere a mudanca e devolve o `lsn` atribuido pela sequencia.

        `pk` default e o proprio `after`: serve para os testes de uma linha so.
        Testes com MAIS de uma linha da mesma `tabela` precisam passar `pk`
        explicito e distinto -- `bronze.merge_do_log` faz `DISTINCT ON (pk)`
        por design (e o que faz o merge ser idempotente sobre reentrega), e
        `pk` igual em duas linhas colapsa as duas em uma so, silenciosamente.
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bronze.change_log (source_table, op, pk, after, captured_at)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, now())
                RETURNING lsn
                """,
                (
                    tabela,
                    op,
                    json.dumps(pk if pk is not None else after),
                    json.dumps(after),
                ),
            )
            return cur.fetchone()[0]

    return _inserir
