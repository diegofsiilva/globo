def test_liveness(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_readiness(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_root_describes_running_api(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json["service"] == "telemetry-backend"
    assert response.json["status"] == "ok"
    assert response.json["endpoints"]["create"] == "POST /api/v1/events"


def test_favicon_does_not_generate_not_found(client):
    response = client.get("/favicon.ico")

    assert response.status_code == 204
