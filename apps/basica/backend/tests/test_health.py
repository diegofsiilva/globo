"""Testes dos endpoints básicos de saúde e descoberta da API."""


def test_liveness(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_readiness(client):
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_root_describes_the_read_api(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json["service"] == "telemetry-read-api"
    assert response.json["status"] == "ok"
    assert "search" in response.json["endpoints"]


def test_root_avisa_que_ingestao_nao_passa_por_aqui(client):
    """A entrada de eventos e o API Gateway; deixar isso explicito evita que
    alguem tente publicar evento nesta API e perca tempo."""
    response = client.get("/")

    assert "ingestao" in response.json["notes"].lower()
    assert "create" not in response.json["endpoints"]


def test_cors_liberado_para_o_dashboard(client):
    """A dashboard e um site estatico em outra origem (Next com output:
    export); sem estes cabecalhos o navegador bloqueia a chamada."""
    response = client.get("/api/v1/events")

    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]
