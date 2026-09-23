"""Testes do Lambda authorizer.

O cliente do Secrets Manager e substituido por um duble no proprio modulo
(`handler._secrets`). Nao ha `moto` aqui: a superficie usada e um unico metodo
que devolve uma string, e um duble de tres linhas testa a mesma coisa sem
somar 30 MB de dependencia a um projeto cujo zip publicado tem 5 KB.
"""

from __future__ import annotations

import hashlib
import json

import pytest

import handler

API_LEITURA = "abc123read"
API_INGESTAO = "def456ing"

TOKEN_DASHBOARD = "d" * 64
TOKEN_INGEST = "i" * 64


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SecretsFalso:
    """Duble do cliente do Secrets Manager."""

    def __init__(self, payload: str | None = None, erro: Exception | None = None) -> None:
        """Configura o que o dublê devolve, ou o erro que levanta."""
        self.payload = payload
        self.erro = erro
        self.chamadas = 0

    def get_secret_value(self, SecretId: str) -> dict:  # noqa: N803 - assinatura do boto3
        """Devolve o segredo, ou levanta o erro configurado."""
        self.chamadas += 1
        if self.erro is not None:
            raise self.erro
        return {"SecretString": self.payload}


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    """Configura as variaveis de ambiente e o duble do Secrets Manager."""
    monkeypatch.setenv("SECRET_ID", "argus/tokens")
    monkeypatch.setenv(
        "AUDIENCIAS_POR_API",
        json.dumps({API_LEITURA: ["dashboard"], API_INGESTAO: ["ingest"]}),
    )
    duble = SecretsFalso(
        json.dumps({"dashboard": _sha(TOKEN_DASHBOARD), "ingest": _sha(TOKEN_INGEST)})
    )
    monkeypatch.setattr(handler, "_secrets", duble)
    return duble


def _evento(api_id: str, autorizacao: str | None = None) -> dict:
    cabecalhos = {"authorization": autorizacao} if autorizacao is not None else {}
    arn = f"arn:aws:execute-api:us-east-1:000000000000:{api_id}/$default/GET/api/v1/sources"
    return {
        "routeArn": arn,
        "headers": cabecalhos,
        "requestContext": {"requestId": "req-1"},
    }


# --------------------------------------------------------------------------- #
# Caminho feliz
# --------------------------------------------------------------------------- #


def test_token_de_leitura_autoriza_na_api_de_leitura():
    resposta = handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)

    assert resposta["isAuthorized"] is True
    assert resposta["context"] == {"audience": "dashboard"}


def test_token_de_ingestao_autoriza_na_api_de_ingestao():
    resposta = handler.lambda_handler(_evento(API_INGESTAO, f"Bearer {TOKEN_INGEST}"), None)

    assert resposta["isAuthorized"] is True
    assert resposta["context"] == {"audience": "ingest"}


def test_esquema_bearer_e_case_insensitive():
    """A RFC 7235 define o esquema como case-insensitive; `bearer` tambem vale."""
    resposta = handler.lambda_handler(_evento(API_LEITURA, f"bearer {TOKEN_DASHBOARD}"), None)

    assert resposta["isAuthorized"] is True


# --------------------------------------------------------------------------- #
# Negacoes
# --------------------------------------------------------------------------- #


def test_token_invalido_nega():
    resposta = handler.lambda_handler(_evento(API_LEITURA, "Bearer " + "x" * 64), None)

    assert resposta == {"isAuthorized": False}


def test_sem_cabecalho_nega():
    """Na AWS o gateway ja teria respondido 401 sem invocar a funcao; aqui o
    caso existe para garantir que uma invocacao direta tambem nega."""
    resposta = handler.lambda_handler(_evento(API_LEITURA), None)

    assert resposta == {"isAuthorized": False}


def test_esquema_diferente_de_bearer_nega():
    resposta = handler.lambda_handler(_evento(API_LEITURA, f"Basic {TOKEN_DASHBOARD}"), None)

    assert resposta == {"isAuthorized": False}


def test_token_vazio_apos_bearer_nega():
    resposta = handler.lambda_handler(_evento(API_LEITURA, "Bearer    "), None)

    assert resposta == {"isAuthorized": False}


def test_token_de_leitura_nao_serve_para_ingestao():
    """A separacao por audiencia e o que impede que o token exposto no
    navegador do operador valha tambem para injetar evento."""
    resposta = handler.lambda_handler(_evento(API_INGESTAO, f"Bearer {TOKEN_DASHBOARD}"), None)

    assert resposta == {"isAuthorized": False}


def test_token_de_ingestao_nao_serve_para_leitura():
    resposta = handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_INGEST}"), None)

    assert resposta == {"isAuthorized": False}


def test_api_fora_do_mapa_nega():
    """Falha fechada: uma API nova que ainda nao entrou em `AUDIENCIAS_POR_API`
    nao deve passar a aceitar qualquer token."""
    resposta = handler.lambda_handler(
        _evento("api-desconhecida", f"Bearer {TOKEN_DASHBOARD}"), None
    )

    assert resposta == {"isAuthorized": False}


def test_segredo_indisponivel_nega(monkeypatch):
    """Indisponibilidade do Secrets Manager nao pode virar acesso aberto."""
    monkeypatch.setattr(handler, "_secrets", SecretsFalso(erro=RuntimeError("timeout")))

    resposta = handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)

    assert resposta == {"isAuthorized": False}


def test_segredo_malformado_nega(monkeypatch):
    monkeypatch.setattr(handler, "_secrets", SecretsFalso("nao e json"))

    resposta = handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)

    assert resposta == {"isAuthorized": False}


def test_configuracao_de_audiencias_invalida_nega(monkeypatch):
    monkeypatch.setenv("AUDIENCIAS_POR_API", "{nao e json")

    resposta = handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)

    assert resposta == {"isAuthorized": False}


# --------------------------------------------------------------------------- #
# Segredo e rotacao
# --------------------------------------------------------------------------- #


def test_cada_invocacao_le_a_versao_atual_do_segredo(ambiente):
    """O cache do gateway basta; o processo nao pode reter hash rotacionado."""
    for _ in range(5):
        handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)

    assert ambiente.chamadas == 5


def test_rotacao_do_segredo_invalida_o_token_antigo_imediatamente(ambiente):
    """A invocacao seguinte ja consulta os hashes novos, sem esperar TTL local."""
    assert handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)[
        "isAuthorized"
    ]

    novo = "n" * 64
    ambiente.payload = json.dumps({"dashboard": _sha(novo), "ingest": _sha(TOKEN_INGEST)})

    assert handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None) == {
        "isAuthorized": False
    }
    assert handler.lambda_handler(_evento(API_LEITURA, f"Bearer {novo}"), None)["isAuthorized"]


def test_hash_maiusculo_no_segredo_ainda_casa():
    """Hexadecimal e case-insensitive; o segredo pode ter sido gravado por uma
    ferramenta que emite maiuscula, e isso nao deve derrubar a autenticacao."""
    handler._secrets.payload = json.dumps({"dashboard": _sha(TOKEN_DASHBOARD).upper()})

    resposta = handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)

    assert resposta["isAuthorized"] is True


def test_nenhum_token_aparece_no_log(caplog):
    """RNF09/RNF10: o log registra a decisao, nunca a credencial."""
    with caplog.at_level("INFO"):
        handler.lambda_handler(_evento(API_LEITURA, f"Bearer {TOKEN_DASHBOARD}"), None)
        handler.lambda_handler(_evento(API_LEITURA, "Bearer " + "x" * 64), None)

    registrado = caplog.text
    assert TOKEN_DASHBOARD not in registrado
    assert "x" * 64 not in registrado
    assert "authorizer_allow" in registrado
    assert "authorizer_deny" in registrado
