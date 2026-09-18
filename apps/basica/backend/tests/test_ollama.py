"""Refinamento Ollama com lastro exclusivo na hipotese publicada."""

import json

import pytest

from telemetry import create_app
from telemetry.domain.exceptions import RefinementUnavailableError
from telemetry.infrastructure.ollama import OllamaHypothesisRefiner


class FakeResponse:
    """Resposta HTTP minima para exercitar o cliente sem rede."""

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        """Abre o contexto da resposta."""
        return self

    def __exit__(self, *_args):
        """Fecha o contexto sem suprimir excecoes."""
        return None

    def read(self, _limit):
        return self.payload


class FakeRepository:
    """Repositorio minimo usado nos testes isolados da rota."""

    pool = object()

    def __init__(self, hypothesis):
        self.hypothesis = hypothesis

    def detail(self, hypothesis_id):
        return self.hypothesis if hypothesis_id == self.hypothesis["hypothesis_id"] else None


class FakeRefiner:
    """Captura a entrada que a rota entrega ao adaptador."""

    def __init__(self):
        self.received = None

    def refine(self, hypothesis, *, question):
        self.received = (hypothesis, question)
        return {
            "hypothesis_id": hypothesis["hypothesis_id"],
            "answerable": True,
            "answer": "Erro alto sustenta a hipotese.",
            "claims": [],
            "limitations": [],
            "sources": [],
            "model": "fake",
            "grounding": "hypothesis_only",
        }


@pytest.fixture
def hypothesis():
    return {
        "hypothesis_id": 42,
        "title": "Falha interna",
        "summary": "Erro corroborado",
        "score": 82,
        "features": [{"feature": "desvio", "value": 0.9}],
        "evidence": [
            {
                "evidence_id": 7,
                "source": "prometheus",
                "metric": "error_rate_pct",
                "explanation": "erro alto",
            }
        ],
        "feedback": [{"note": "nao deve ir ao modelo"}],
        "manifest": {"internal": "nao deve ir ao modelo"},
    }


def _ollama_envelope(content):
    return {"message": {"content": json.dumps(content)}}


def test_refinador_envia_so_fontes_permitidas_e_valida_citacoes(hypothesis):
    captured = {}

    def opener(request, *, timeout):
        captured["request"] = json.loads(request.data)
        captured["timeout"] = timeout
        content = {
            "answerable": True,
            "claims": [
                {
                    "text": "A taxa de erro elevada sustenta a hipotese.",
                    "source_ids": ["hypothesis.summary", "evidence.7"],
                }
            ],
            "limitations": [],
        }
        return FakeResponse(_ollama_envelope(content))

    result = OllamaHypothesisRefiner(
        "http://127.0.0.1:11434", "modelo-teste", timeout_seconds=12, opener=opener
    ).refine(hypothesis, question="O que sustenta a hipotese?")

    assert result["grounding"] == "hypothesis_only"
    assert result["answer"] == "A taxa de erro elevada sustenta a hipotese."
    assert {source["id"] for source in result["sources"]} == {
        "hypothesis.summary",
        "evidence.7",
    }
    prompt = captured["request"]["messages"][1]["content"]
    assert "nao deve ir ao modelo" not in prompt
    assert captured["request"]["options"]["temperature"] == 0
    assert captured["request"]["format"]["additionalProperties"] is False
    assert captured["timeout"] == 12


def test_refinador_recusa_fonte_que_nao_existe(hypothesis):
    content = {
        "answerable": True,
        "claims": [{"text": "Inventado", "source_ids": ["evidence.999"]}],
        "limitations": [],
    }
    refiner = OllamaHypothesisRefiner(
        "http://127.0.0.1:11434",
        "modelo-teste",
        opener=lambda *_args, **_kwargs: FakeResponse(_ollama_envelope(content)),
    )

    with pytest.raises(RefinementUnavailableError, match="fonte inexistente"):
        refiner.refine(hypothesis, question=None)


def test_refinador_responde_de_forma_fixa_quando_contexto_e_insuficiente(hypothesis):
    content = {"answerable": False, "claims": [], "limitations": []}
    refiner = OllamaHypothesisRefiner(
        "http://127.0.0.1:11434",
        "modelo-teste",
        opener=lambda *_args, **_kwargs: FakeResponse(_ollama_envelope(content)),
    )

    result = refiner.refine(hypothesis, question="Qual foi o autor do deploy?")

    assert result["answerable"] is False
    assert "nao contem informacao suficiente" in result["answer"]


def test_rota_entrega_hipotese_publicada_ao_refinador(hypothesis):
    repository = FakeRepository(hypothesis)
    refiner = FakeRefiner()
    app = create_app(
        {"TESTING": True, "OLLAMA_URL": ""},
        repository=repository,
        gold=repository,
        hypotheses=repository,
        signals=repository,
        hypothesis_refiner=refiner,
    )

    response = app.test_client().post(
        "/api/v1/hypotheses/42/refinement",
        json={"question": "  Explique o principal sinal  "},
    )

    assert response.status_code == 200
    assert response.json["grounding"] == "hypothesis_only"
    assert refiner.received == (hypothesis, "Explique o principal sinal")


def test_rota_recusa_pergunta_fora_do_contrato(hypothesis):
    repository = FakeRepository(hypothesis)
    app = create_app(
        {"TESTING": True, "OLLAMA_URL": ""},
        repository=repository,
        gold=repository,
        hypotheses=repository,
        signals=repository,
    )
    client = app.test_client()

    assert client.post("/api/v1/hypotheses/42/refinement", json={"extra": True}).status_code == 422
    assert client.post("/api/v1/hypotheses/42/refinement", json={"question": ""}).status_code == 422
    assert client.post("/api/v1/hypotheses/42/refinement", json={}).status_code == 503
