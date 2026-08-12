from run import build_app


def test_single_entrypoint_supports_typical_create_read_delete_flow():
    app = build_app(
        {
            "TESTING": True,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "USER_ID_HASH_SALT": "test-salt",
        }
    )
    client = app.test_client()
    event_id = "63811f26-0249-4f34-936a-b79e6d9cf857"

    created = client.post(
        "/api/v1/events",
        json={
            "event_id": event_id,
            "timestamp": "2026-07-13T20:04:44Z",
            "event_name": "request",
            "app_env": "production",
        },
    )
    read = client.get(f"/api/v1/events/{event_id}")
    deleted = client.delete(f"/api/v1/events/{event_id}")
    readiness = client.get("/health/ready")

    assert created.status_code == 201
    assert read.status_code == 200
    assert deleted.status_code == 204
    assert readiness.status_code == 200
