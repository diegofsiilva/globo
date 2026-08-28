"""A spec precisa descrever a API que existe, nao a que foi planejada."""

import re

from telemetry.interfaces.openapi import BREAKDOWN_FIELDS, FACET_FIELDS, build_spec


def _openapi_path(rule) -> str:
    """Converte `<int:id>` do Flask em `{id}` do OpenAPI."""
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", str(rule))


def test_spec_e_servida(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json["openapi"].startswith("3.1")
    assert response.json["info"]["title"]


def test_swagger_ui_e_servida(client):
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger" in response.get_data(as_text=True).lower()


def test_servers_vem_do_host_da_requisicao(client):
    """A URL real da API nao pode estar escrita no repositorio."""
    response = client.get("/openapi.json")
    url = response.json["servers"][0]["url"]

    assert "execute-api" not in url
    assert url.startswith("http://localhost")


def test_todas_as_rotas_da_aplicacao_estao_na_spec(app):
    """Trava a divergencia: rota nova sem documentacao quebra o teste."""
    spec = build_spec()
    documentadas = set(spec["paths"])

    reais = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        caminho = str(rule)
        if caminho in {"/", "/favicon.ico", "/docs", "/openapi.json"}:
            continue
        reais.add(_openapi_path(rule))

    faltando = reais - documentadas
    assert not faltando, f"rotas sem documentacao na spec: {sorted(faltando)}"


def test_spec_nao_documenta_rota_inexistente(app):
    spec = build_spec()
    reais = {_openapi_path(rule) for rule in app.url_map.iter_rules() if rule.endpoint != "static"}

    sobrando = set(spec["paths"]) - reais
    assert not sobrando, f"spec documenta rota que nao existe: {sorted(sobrando)}"


def test_valores_aceitos_vem_das_constantes_do_codigo(client):
    """A spec importa as mesmas constantes que o adaptador valida, entao a
    documentacao nao consegue divergir do que a API aceita de verdade.
    """
    spec = client.get("/openapi.json").json

    dimension = next(
        p
        for p in spec["paths"]["/api/v1/metrics/breakdown"]["get"]["parameters"]
        if p["name"] == "dimension"
    )
    assert set(dimension["schema"]["enum"]) == BREAKDOWN_FIELDS

    field = next(
        p for p in spec["paths"]["/api/v1/facets"]["get"]["parameters"] if p["name"] == "field"
    )
    assert set(field["schema"]["items"]["enum"]) == FACET_FIELDS


def test_spec_documenta_somente_a_escrita_estreita_de_feedback(client):
    """A unica mutacao publica e o feedback idempotente de hipotese."""
    spec = client.get("/openapi.json").json

    writes = set()
    for caminho, operacoes in spec["paths"].items():
        for method in set(operacoes) - {"get"}:
            writes.add((method, caminho))
    assert writes == {("post", "/api/v1/hypotheses/{hypothesis_id}/feedback")}


def test_spec_nao_expoe_campo_sensivel_como_filtravel(client):
    spec = client.get("/openapi.json").json
    corpo = str(spec)

    assert "user_id_hash" in corpo  # o hash e documentado
    field = next(
        p for p in spec["paths"]["/api/v1/facets"]["get"]["parameters"] if p["name"] == "field"
    )
    assert "user_id" not in field["schema"]["items"]["enum"]
