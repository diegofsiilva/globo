"""Fixtures compartilhadas pelos testes do worker de ingestão."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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


@pytest.fixture
def aws(monkeypatch, tmp_path):
    """Sobe SQS (fila + DLQ) e DynamoDB em memoria e devolve a Config pronta."""
    from moto import mock_aws

    with mock_aws():
        import boto3

        from argus_worker.config import Config

        sqs = boto3.client("sqs", region_name="us-east-1")
        queue_url = sqs.create_queue(QueueName="argus-events")["QueueUrl"]
        dlq_url = sqs.create_queue(QueueName="argus-events-dlq")["QueueUrl"]

        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName="argus-events",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": n, "AttributeType": "S"}
                for n in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk")
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "gsi1",
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "gsi2",
                    "KeySchema": [
                        {"AttributeName": "gsi2pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi2sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        )

        config = Config(
            queue_url=queue_url,
            dlq_url=dlq_url,
            table_name="argus-events",
            region="us-east-1",
            wait_time_seconds=0,  # sem long polling: teste nao pode ficar parado
            heartbeat_path=str(tmp_path / "heartbeat"),
            gsi1_shards=4,
        )

        yield type(
            "AwsHarness",
            (),
            {"sqs": sqs, "dynamodb": dynamodb, "config": config},
        )


@pytest.fixture
def consumer(aws):
    from argus_worker.consumer import Consumer
    from argus_worker.observability import Metrics
    from argus_worker.repository import EventRepository

    return Consumer(
        config=aws.config,
        sqs_client=aws.sqs,
        repository=EventRepository(aws.dynamodb, aws.config.table_name),
        metrics=Metrics("Argus/Test", "test-worker"),
    )
