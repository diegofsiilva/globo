"""Fixtures dos testes.

Os itens gravados aqui usam o formato EXATO que o worker de ingestao escreve
(ver worker/src/argus_worker/keys.py). Isso e proposital: se os testes usassem
um formato conveniente, eles passariam enquanto a API quebra contra o banco
real -- que foi exatamente o defeito encontrado no backend anterior.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import boto3
import pytest
from moto import mock_aws

from telemetry import create_app
from telemetry.infrastructure.dynamo import DynamoEventRepository

TABLE_NAME = "argus-events-test"
SHARDS = 4
SALT = "test-salt"

# As fixtures sao os eventos reais do export, todos de 2026-07-13. Uma consulta
# sem periodo fecha a janela no "agora", e o fan-out da GSI1 mantem apenas os
# `max_days_fanout` dias mais recentes -- entao, com o relogio real, esses
# testes passavam por proximidade da data e falhavam 31 dias depois, sem
# nenhuma mudanca de codigo. O relogio fica fixo um dia depois das fixtures.
REFERENCE_NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)

# As fixtures dos seis eventos reais sao as mesmas que o worker usa: uma fonte
# de verdade so para os dois lados do pipeline.
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "worker" / "tests" / "fixtures"


def _to_decimal(value: Any) -> Any:
    """float -> Decimal, como o worker faz antes de gravar.

    O DynamoDB nao tem float. Via str para nao arrastar o residuo de IEEE-754:
    Decimal(0.1) e 0.1000000000000000055, ja Decimal("0.1") e exatamente 0.1.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_decimal(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_to_decimal(inner) for inner in value]
    return value


def build_item(event: dict, *, ingested_at: datetime | None = None) -> dict:
    """Reproduz o item do DynamoDB a partir de um evento canonico.

    Espelha worker/src/argus_worker/keys.py::build_item. Duplicar essa logica
    aqui e o preco de o worker e a API serem processos separados; o teste
    test_formato_do_item_espelha_o_worker trava a duplicacao.
    """
    ingested_at = ingested_at or datetime.now(UTC)
    payload = {key: value for key, value in event.items() if value is not None}
    payload.pop("event_id", None)
    event_id = (
        event.get("event_id")
        or hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
    )

    occurred = datetime.fromisoformat(str(event["timestamp"]).replace("Z", "+00:00"))
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=UTC)
    occurred = occurred.astimezone(UTC)

    ts = occurred.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    short = event_id[:12]
    day = occurred.strftime("%Y-%m-%d")
    shard = int(event_id[:8], 16) % SHARDS

    item = {key: _to_decimal(value) for key, value in event.items()}
    item.update(
        {
            "event_id": event_id,
            "pk": f"SESSION#{event['session_id']}",
            "sk": f"{ts}#{short}",
            "gsi1pk": f"EVT#{event['event_name']}#{day}#{shard}",
            "gsi1sk": f"{ts}#{short}",
            "gsi2pk": f"DEV#{event['device_id']}",
            "gsi2sk": f"{ts}#{short}",
            "event_date": day,
            "ingested_at": ingested_at.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "expires_at": int((ingested_at + timedelta(days=90)).timestamp()),
        }
    )
    return {key: value for key, value in item.items() if value is not None}


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch):
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_REGION": "us-east-1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture(scope="session")
def sample_events() -> dict[str, dict]:
    events = {}
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        event = json.loads(path.read_text(encoding="utf-8"))
        events[event["event_name"]] = event
    assert events, f"nenhuma fixture em {FIXTURES_DIR}"
    return events


@pytest.fixture
def table():
    """Tabela com o mesmo schema do Terraform (ver infra/dynamodb.tf)."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        created = dynamodb.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": name, "AttributeType": "S"}
                for name in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk")
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
        yield created


@pytest.fixture
def seeded(table, sample_events):
    """Tabela com os seis eventos reais gravados."""
    with table.batch_writer() as batch:
        for event in sample_events.values():
            batch.put_item(Item=build_item(event))
    return table


@pytest.fixture
def repository(table):
    return DynamoEventRepository(
        table,
        gsi1_shards=SHARDS,
        user_id_hash_salt=SALT,
        default_window_hours=24 * 400,
        clock=lambda: REFERENCE_NOW,
    )


@pytest.fixture
def app(table):
    return create_app(
        {"TESTING": True, "USER_ID_HASH_SALT": SALT},
        repository=DynamoEventRepository(
            table,
            gsi1_shards=SHARDS,
            user_id_hash_salt=SALT,
            default_window_hours=24 * 400,
            clock=lambda: REFERENCE_NOW,
        ),
    )


@pytest.fixture
def client(app):
    return app.test_client()
