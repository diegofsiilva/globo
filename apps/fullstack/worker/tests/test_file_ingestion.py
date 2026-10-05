"""Upload e processamento reais: PostgreSQL, CSV, Parquet e recuperação."""

import hashlib
import io
import json
import uuid
from datetime import UTC, datetime

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from argus_worker.files.api import create_app
from argus_worker.files.parser import parse_file
from argus_worker.files.processor import process_one
from argus_worker.files.store import FileStore
from argus_worker.repository import EventRepository

MAPPING = {k: k for k in ("timestamp", "event_name", "session_id", "device_id")}
CAPTURED = datetime(2026, 7, 24, 12, tzinfo=UTC)


@pytest.fixture
def harness(db):
    # Dados sintéticos e apenas no argus_test, conforme a fixture compartilhada.
    with db.connection() as conn:
        conn.execute("TRUNCATE ingest.file_job")
    token = uuid.uuid4().hex + uuid.uuid4().hex
    owner = hashlib.sha256(token.encode()).hexdigest()
    app = create_app(db, owner)
    app.config["TESTING"] = True
    return (
        db,
        app.test_client(),
        FileStore(db),
        owner,
        {"Authorization": f"Bearer {token}"},
    )


def csv_content(session="file-test", invalid=False, count=12):
    rows = [",".join(MAPPING)]
    for i in range(count):
        device = "" if invalid and i == count - 1 else "device-001"
        rows.append(f"2026-07-24T10:00:{i:02d}Z,session,{session},{device}")
    return ("\n".join(rows) + "\n").encode()


def upload(harness, content, filename="events.csv", mapping=None):
    _, client, _, _, headers = harness
    return client.post(
        "/ingestion/v1/files",
        headers=headers,
        data={
            "file": (io.BytesIO(content), filename),
            "mapping": json.dumps(mapping or MAPPING),
        },
    )


def test_csv_upload_processes_beyond_preview_and_records_rejections(harness):
    db, client, store, owner, headers = harness
    response = upload(harness, csv_content(invalid=True))
    assert response.status_code == 202
    job_id = response.json["job"]["id"]
    assert response.json["job"]["status"] == "na_fila"
    assert process_one(store)
    result = client.get(f"/ingestion/v1/jobs/{job_id}", headers=headers).json["job"]
    assert result["status"] == "concluido_com_rejeicoes"
    assert (result["total"], result["inserted"], result["rejected"]) == (12, 11, 1)
    assert result["errors"][0]["linha"] == 12
    assert "device-001" not in json.dumps(result)
    row = db.fetch_one(
        "SELECT count(*) AS n FROM bronze.event WHERE session_id='file-test'"
    )
    assert row["n"] == 11
    assert (
        db.fetch_one("SELECT content FROM ingest.file_job WHERE id=%s", (job_id,))[
            "content"
        ]
        is None
    )
    assert store.get(owner, job_id)["inserted"] == 11


def test_parquet_preserves_extra_and_large_identifier(harness):
    db, _, store, _, _ = harness
    data = {
        "timestamp": [CAPTURED],
        "event_name": ["tipo_novo"],
        "session_id": ["parquet-test"],
        "device_id": ["000001"],
        "extra": [2**60 + 1],
    }
    buffer = io.BytesIO()
    pq.write_table(pa.table(data), buffer, compression="snappy")
    response = upload(harness, buffer.getvalue(), "events.parquet")
    assert response.status_code == 202
    assert process_one(store)
    row = db.fetch_one(
        "SELECT device_id,payload FROM bronze.event WHERE session_id='parquet-test'"
    )
    assert row["device_id"] == "000001"
    assert row["payload"]["_file_extra"]["extra"] == 2**60 + 1


def test_upload_and_event_idempotence_are_independent(harness):
    db, _, store, _, _ = harness
    content = csv_content(count=2)
    first = upload(harness, content).json["job"]
    second = upload(harness, content, "renamed.csv").json["job"]
    assert first["id"] == second["id"]
    assert process_one(store)
    # Mesmo evento em arquivo com bytes diferentes: a chave bronze deduplica.
    another = upload(harness, content + b"\n").json["job"]
    assert another["id"] != first["id"]
    assert process_one(store)
    job = store.get(harness[3], another["id"])
    assert (job["inserted"], job["duplicates"]) == (0, 2)
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"] == 2


def test_fencing_blocks_stale_worker_and_recovers_expired_lease(harness):
    db, _, store, owner, _ = harness
    job_id = upload(harness, csv_content(count=1)).json["job"]["id"]
    old = store.claim()
    assert store.claim() is None
    with db.connection() as conn:
        conn.execute(
            "UPDATE ingest.file_job "
            "SET updated_at=clock_timestamp()-interval '6 minutes' "
            "WHERE id=%s",
            (job_id,),
        )
    new = store.claim()
    assert old["lease"] != new["lease"]
    rows, total, rejected, errors = parse_file(
        bytes(new["content"]), "csv", MAPPING, ",", new["available_at"]
    )
    assert store.finish(old, rows, total, rejected, errors) is False
    assert store.finish(new, rows, total, rejected, errors) is True
    assert store.get(owner, job_id)["attempts"] == 2
    result = db.fetch_one("SELECT _captured_at FROM bronze.event")
    assert result["_captured_at"] == new["available_at"]


def test_event_insert_and_job_result_rollback_together_then_retry(harness, monkeypatch):
    db, client, store, owner, headers = harness
    job_id = upload(harness, csv_content(count=1)).json["job"]["id"]
    original = EventRepository.put_many

    def interrupted(self, rows, *, connection=None):
        original(self, rows, connection=connection)
        raise RuntimeError("interrupção sintética após SQL real")

    with monkeypatch.context() as scoped:
        scoped.setattr(EventRepository, "put_many", interrupted)
        assert process_one(store)
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"] == 0
    assert store.get(owner, job_id)["status"] == "falhou"
    assert (
        client.post(f"/ingestion/v1/jobs/{job_id}/retry", headers=headers).status_code
        == 202
    )
    assert process_one(store)
    assert store.get(owner, job_id)["inserted"] == 1


@pytest.mark.parametrize(
    "content,filename",
    [
        (b"not parquet", "x.parquet"),
        (b'timestamp,event_name,session_id,device_id\n"unterminated', "x.csv"),
        (b"timestamp,event_name,session_id,device_id\n", "x.csv"),
    ],
)
def test_invalid_files_are_terminal_and_release_bytes(harness, content, filename):
    db, client, store, owner, headers = harness
    job_id = upload(harness, content, filename).json["job"]["id"]
    assert process_one(store)
    assert store.get(owner, job_id)["status"] == "rejeitado"
    assert (
        client.post(f"/ingestion/v1/jobs/{job_id}/retry", headers=headers).status_code
        == 409
    )
    assert (
        db.fetch_one("SELECT content FROM ingest.file_job WHERE id=%s", (job_id,))[
            "content"
        ]
        is None
    )


def test_auth_limits_and_owner_isolation(harness):
    db, client, _, _, headers = harness
    assert client.get("/ingestion/v1/session").status_code == 401
    assert client.get("/ingestion/v1/session", headers=headers).status_code == 200
    job_id = upload(harness, csv_content()).json["job"]["id"]
    other = uuid.uuid4().hex + uuid.uuid4().hex
    other_client = create_app(
        db, hashlib.sha256(other.encode()).hexdigest()
    ).test_client()
    assert (
        other_client.get(
            f"/ingestion/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {other}"}
        ).status_code
        == 404
    )
    assert upload(harness, b"x", "x.txt").status_code == 422
    assert upload(harness, b"").status_code == 422
    assert upload(harness, b"x", mapping={"timestamp": "a"}).status_code == 422
    for i in range(9):
        assert upload(harness, csv_content(session=str(i))).status_code == 202
    assert upload(harness, csv_content(session="overflow")).status_code == 422
    assert (
        client.get("/ingestion/openapi.json", headers=headers).json["openapi"] == "3.1.0"
    )


def test_api_fails_closed_without_credential(monkeypatch):
    monkeypatch.delenv("DASHBOARD_TOKEN_SHA256", raising=False)
    with pytest.raises(RuntimeError, match="DASHBOARD_TOKEN_SHA256"):
        create_app()


def test_resending_expired_transient_failure_restores_content(harness):
    db, _, store, owner, _ = harness
    content = csv_content(count=1)
    job_id = upload(harness, content).json["job"]["id"]
    with db.connection() as conn:
        conn.execute(
            "UPDATE ingest.file_job SET status='falhou', content=NULL WHERE id=%s",
            (job_id,),
        )
    response = upload(harness, content)
    assert response.json["job"]["id"] == job_id
    assert response.json["job"]["status"] == "na_fila"
    assert process_one(store)
    assert store.get(owner, job_id)["inserted"] == 1


def test_cors_preflight_requires_explicit_origin(harness, monkeypatch):
    monkeypatch.setenv("INGEST_CORS_ORIGINS", "http://frontend.test")
    client = create_app(harness[0], harness[3]).test_client()
    response = client.options(
        "/ingestion/v1/files", headers={"Origin": "http://frontend.test"}
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "http://frontend.test"
    assert (
        client.options(
            "/ingestion/v1/files", headers={"Origin": "http://other.test"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration", "NaN"),
        ("request_status", str(2**40)),
        ("timestamp", "2026-02-30T12:00:00Z"),
        ("media_ads", "yes"),
    ],
)
def test_server_validates_values_independently_of_browser(field, value):
    mapping = {**MAPPING, field: field}
    data = {
        "timestamp": "2026-07-24T10:00:00Z",
        "event_name": "session",
        "session_id": "parser-test",
        "device_id": "001",
        field: value,
    }
    content = (",".join(data) + "\n" + ",".join(data.values())).encode()
    rows, total, rejected, errors = parse_file(content, "csv", mapping, ",", CAPTURED)
    assert not rows and total == rejected == 1
    assert errors[0]["campo"] == field
