"""Consulta cancelada pelo `statement_timeout` vira 504, e não 500."""

from psycopg.errors import QueryCanceled

from telemetry.app import create_app


class RepositorioLento:
    """Repositório que estoura o tempo em qualquer consulta de hipóteses."""

    def list(self, **_filtros):
        """Simula o cancelamento que o PostgreSQL devolve no timeout."""
        raise QueryCanceled("canceling statement due to statement timeout")


def _client():
    repositorio = RepositorioLento()
    app = create_app(
        {"TESTING": True, "OLLAMA_URL": ""},
        repository=repositorio,
        gold=repositorio,
        hypotheses=repositorio,
        signals=repositorio,
    )
    return app.test_client()


def test_timeout_do_banco_responde_504_com_problem_details():
    response = _client().get("/api/v1/hypotheses")

    assert response.status_code == 504
    assert response.content_type == "application/problem+json"
    assert response.json["title"] == "Query timeout"
    # A causa diz o que fazer: sem isso, o operador le "erro interno" e espera
    # alguem consertar um defeito que nao existe.
    assert "Restrinja o recorte" in response.json["detail"]
    assert response.json["instance"] == "/api/v1/hypotheses"


def test_timeout_nao_vaza_o_texto_do_banco():
    corpo = _client().get("/api/v1/hypotheses").get_data(as_text=True)

    assert "canceling statement" not in corpo
