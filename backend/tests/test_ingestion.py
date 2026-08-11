import csv
import io


def valid_event(**overrides):
    event = {
        "timestamp": "2026-07-13T20:04:44Z",
        "event_name": "request",
        "duration": 0.033,
        "app_env": "production",
        "device_os": "Tizen",
        "user_id": "sensitive-user",
        "request_headers": {
            "authorization": "secret",
            "accept": "application/json",
        },
    }
    event.update(overrides)
    return event


def test_ingests_and_queries_json_event(client):
    response = client.post("/api/v1/events", json=valid_event())

    assert response.status_code == 201
    assert response.json["accepted"] == 1

    query = client.get("/api/v1/events?event_name=request&device_os=Tizen")
    assert query.status_code == 200
    assert query.json["pagination"]["total"] == 1
    stored = query.json["items"][0]
    assert stored["duration_ms"] == 33.0
    assert stored["user_id_hash"] != "sensitive-user"
    assert "authorization" not in stored["attributes"]["request_headers"]


def test_valid_events_survive_invalid_event_in_batch(client):
    response = client.post(
        "/api/v1/events",
        json=[valid_event(), valid_event(event_name="unknown")],
    )

    assert response.status_code == 207
    assert response.json["accepted"] == 1
    assert response.json["rejected"] == 1
    assert response.json["errors"][0]["row"] == 2


def test_ingests_csv_with_embedded_json(client):
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["Timestamp", "Event Name", "Request Headers", "Request Status"],
    )
    writer.writeheader()
    writer.writerow(
        {
            "Timestamp": "July 13, 2026 20:04:44",
            "Event Name": "request",
            "Request Headers": '{"accept":"application/json","authorization":"secret"}',
            "Request Status": "200",
        }
    )

    response = client.post("/api/v1/events", data=output.getvalue(), content_type="text/csv")

    assert response.status_code == 201
    assert response.json["accepted"] == 1


def test_rejects_invalid_media_type(client):
    response = client.post("/api/v1/events", data="event", content_type="text/plain")

    assert response.status_code == 415
    assert response.content_type == "application/problem+json"


def test_returns_facets(client):
    client.post("/api/v1/events", json=valid_event())

    response = client.get("/api/v1/events/facets?field=event_name&field=device_os")

    assert response.status_code == 200
    assert response.json["facets"] == {"device_os": ["Tizen"], "event_name": ["request"]}


def test_returns_metrics_with_cumulative_filters(client):
    client.post("/api/v1/events", json=valid_event(duration=0.030))
    client.post("/api/v1/events", json=valid_event(duration=0.050))
    client.post("/api/v1/events", json=valid_event(event_name="error", duration=None))

    response = client.get("/api/v1/metrics?event_name=request&app_env=production")

    assert response.status_code == 200
    assert response.json == {
        "total": 2,
        "by_event_name": [{"event_name": "request", "count": 2, "average_duration_ms": 40.0}],
    }


def test_duplicate_event_id_is_idempotent(client):
    event = valid_event(event_id="63811f26-0249-4f34-936a-b79e6d9cf857")

    first = client.post("/api/v1/events", json=event)
    second = client.post("/api/v1/events", json=event)
    query = client.get("/api/v1/events")

    assert first.status_code == 201
    assert second.status_code == 201
    assert query.json["pagination"]["total"] == 1


def test_rejects_empty_csv(client):
    response = client.post("/api/v1/events", data="Timestamp,Event Name\n", content_type="text/csv")

    assert response.status_code == 422
