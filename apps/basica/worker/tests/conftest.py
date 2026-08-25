"""Fixtures dos testes dos workers de ingestao.

Os testes de banco rodam contra um PostgreSQL DE VERDADE, e nao contra um duble.
O motivo e que a parte dificil deste worker mora no SQL: a regra do `_lsn`
maior, o `ON CONFLICT ... WHERE`, o `jsonb_populate_record` que joga coluna
desconhecida no `_extra`. Um duble que respondesse "ok" a tudo isso testaria
apenas o duble.

Suba o banco com `make db-local` (ou aponte TEST_DATABASE_URL para o seu). Sem
ele, os testes de banco sao PULADOS, nao quebrados -- os de validacao pura
(models, keys, changes) continuam rodando em qualquer maquina.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
TOOLS = Path(__file__).resolve().parents[2] / "tools"


@pytest.fixture(autouse=True)
def _fake_aws_credentials(monkeypatch):
    """Impede que o boto3 alcance credencial real durante os testes."""
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_REGION": "us-east-1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture(scope="session")
def sample_events() -> dict[str, dict]:
    """Os seis eventos reais exportados do BI, ja convertidos para JSON."""
    events = {}
    for path in sorted(FIXTURES.glob("*.json")):
        events[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    assert events, f"nenhuma fixture em {FIXTURES}"
    return events


# --------------------------------------------------------------------------- #
# Banco
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL do PostgreSQL de teste, ou pula a suite de banco."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL nao definida (rode `make db-local`)")

    # O Makefile aponta para a porta local por padrao. Sem esta sondagem, Docker
    # desligado virava dezenas de erros de setup em vez dos skips prometidos no
    # runbook, escondendo o resultado dos testes unitarios que nao usam banco.
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
    """Pool de conexao, com o banco limpo antes de cada teste.

    A limpeza e TRUNCATE e nao DROP/CREATE: recriar 500 particoes por teste
    levaria segundos cada. `RESTART IDENTITY` zera a sequencia do `lsn`, o que
    torna os numeros previsiveis nas asserts.
    """
    from argus_common import Database

    banco = Database(_migrated, min_size=1, max_size=2, application_name="teste")
    with banco.connection() as conn:
        conn.execute(
            """
            TRUNCATE bronze.change_log, bronze.event, bronze.signal_bucket,
                     bronze.signal_point, bronze.live_event, bronze.incidents,
                     bronze.incident_label
              RESTART IDENTITY CASCADE
            """
        )
        conn.execute("SELECT sim.set_clock(timestamptz '2026-07-24 12:00:00+00', 1)")
    yield banco
    banco.close()


# --------------------------------------------------------------------------- #
# SQS
# --------------------------------------------------------------------------- #


@pytest.fixture
def aws(monkeypatch, tmp_path, database_url):
    """Sobe SQS em memoria (moto) e devolve as Config dos dois workers."""
    from moto import mock_aws

    with mock_aws():
        import boto3

        from argus_worker.config import Config

        sqs = boto3.client("sqs", region_name="us-east-1")
        filas = {
            nome: sqs.create_queue(QueueName=nome)["QueueUrl"]
            for nome in (
                "argus-events",
                "argus-events-dlq",
                "argus-changes",
                "argus-changes-dlq",
            )
        }

        comum = {
            "database_url": database_url,
            # Sem long polling: o teste nao pode ficar 20s parado esperando uma
            # fila que ele mesmo sabe estar vazia.
            "wait_time_seconds": 0,
            "heartbeat_path": str(tmp_path / "heartbeat"),
        }

        yield type(
            "AwsHarness",
            (),
            {
                "sqs": sqs,
                "filas": filas,
                "config_merge": Config(
                    modo="merge",
                    queue_url=filas["argus-changes"],
                    dlq_url=filas["argus-changes-dlq"],
                    **comum,
                ),
                "config_event": Config(
                    modo="event",
                    queue_url=filas["argus-events"],
                    dlq_url=filas["argus-events-dlq"],
                    **comum,
                ),
            },
        )


def _partes(config, aws, tmp_path):
    """Monta as dependencias comuns aos dois consumidores."""
    from argus_common import Heartbeat, Metrics, ShutdownSignal

    return {
        "config": config,
        "sqs_client": aws.sqs,
        "metrics": Metrics("Argus/Test", "test-worker"),
        "heartbeat": Heartbeat(config.heartbeat_path),
        "shutdown": ShutdownSignal(),
    }


@pytest.fixture
def merge_consumer(aws, db, tmp_path):
    """Merge worker pronto, ligado ao banco de teste."""
    from argus_worker.consumer import ChangeConsumer
    from argus_worker.repository import ChangeRepository

    return ChangeConsumer(
        repository=ChangeRepository(db), **_partes(aws.config_merge, aws, tmp_path)
    )


@pytest.fixture
def event_consumer(aws, db, tmp_path):
    """Event worker pronto, ligado ao banco de teste."""
    from argus_worker.consumer import EventConsumer
    from argus_worker.repository import EventRepository

    return EventConsumer(
        repository=EventRepository(db), **_partes(aws.config_event, aws, tmp_path)
    )
