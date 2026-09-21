"""Testes da validação de token Bearer feita dentro do Flask.

Estes testes **não** dependem do PostgreSQL, ao contrário do resto da suíte. A
autenticação roda no `before_request`, antes de qualquer rota tocar o banco, e
os repositórios injetados aqui existem só para que `create_app` não exija
`DATABASE_URL`. Assim a proteção continua verificável numa máquina sem o
`make db-local` no ar.

O que estes testes protegem, concretamente: a API saiu do API Gateway (que tinha
um Lambda authorizer) para um Application Load Balancer (que não tem). Uma
regressão aqui não quebra nada de forma visível — ela apenas deixa a API aberta.
"""

import pytest

from telemetry import create_app
from telemetry.config import TestConfig
from telemetry.interfaces.auth import hash_do_token

TOKEN = "token-de-teste-com-entropia-suficiente"
HASH = hash_do_token(TOKEN)


class _RepositorioVazio:
    """Dublê mínimo: os testes de auth nunca chegam a exercitar o repositório."""

    pool = None

    def ping(self) -> bool:
        """Responde ao `/health/ready` sem banco.

        Returns:
            bool: Sempre `True`.
        """
        return True


def _app(**config):
    """Monta uma aplicação com repositórios dublês e a configuração pedida.

    A configuração é passada **para** `create_app`, e não aplicada depois: a
    checagem de token é registrada durante a criação da aplicação e lê a config
    naquele momento. Alterá-la em seguida não teria efeito -- que é exatamente
    como o `Config` funciona em produção, lido do ambiente na importação.

    Args:
        **config: Chaves a sobrepor no `TestConfig`.

    Returns:
        Flask: Aplicação pronta, sem dependência de banco.
    """
    repo = _RepositorioVazio()
    valores = {
        chave: getattr(TestConfig, chave)
        for chave in dir(TestConfig)
        if chave.isupper()
    }
    valores.update(config)
    return create_app(valores, repository=repo, gold=repo, hypotheses=repo, signals=repo)


def _cliente(**config):
    """Cliente de teste com a autenticação ligada e o hash do token conhecido.

    Args:
        **config: Chaves extras de configuração.

    Returns:
        FlaskClient: Cliente pronto para as requisições do teste.
    """
    base = {"AUTH_REQUIRED": "1", "DASHBOARD_TOKEN_SHA256": HASH}
    base.update(config)
    return _app(**base).test_client()


# --------------------------------------------------------------------------- #
# Desligada por padrão
# --------------------------------------------------------------------------- #


def test_sem_auth_required_a_api_nao_exige_token():
    """O padrão é desligado: `make api`, os testes e o e2e sobem sem segredo."""
    cliente = _app().test_client()

    assert cliente.get("/health/live").status_code == 200
    # Sem token e sem 401: a checagem sequer foi registrada.
    assert cliente.get("/api/v1/events").status_code != 401


# --------------------------------------------------------------------------- #
# Falha fechada
# --------------------------------------------------------------------------- #


def test_auth_required_sem_hash_recusa_subir():
    """Ligar a exigência sem configurar o hash não pode resultar numa API que se
    acha protegida e não está -- o modo de falha mais caro possível aqui.
    """
    with pytest.raises(RuntimeError, match="DASHBOARD_TOKEN_SHA256"):
        _app(AUTH_REQUIRED="1", DASHBOARD_TOKEN_SHA256="")


# --------------------------------------------------------------------------- #
# 401: cliente desconfigurado
# --------------------------------------------------------------------------- #


def test_sem_cabecalho_responde_401():
    resposta = _cliente().get("/api/v1/events")

    assert resposta.status_code == 401
    assert resposta.content_type == "application/problem+json"
    assert resposta.json["status"] == 401


def test_esquema_errado_responde_401():
    """`Basic` não é Bearer: cabeçalho presente, mas inutilizável."""
    resposta = _cliente().get("/api/v1/events", headers={"Authorization": "Basic abc"})

    assert resposta.status_code == 401


def test_bearer_sem_valor_responde_401():
    resposta = _cliente().get("/api/v1/events", headers={"Authorization": "Bearer   "})

    assert resposta.status_code == 401


# --------------------------------------------------------------------------- #
# 403: credencial inválida
# --------------------------------------------------------------------------- #


def test_token_errado_responde_403():
    """A distinção 401/403 é o que separa, no CloudWatch, cliente mal
    configurado de tentativa com credencial inválida.
    """
    resposta = _cliente().get("/api/v1/events", headers={"Authorization": "Bearer errado"})

    assert resposta.status_code == 403
    assert resposta.json["status"] == 403


# --------------------------------------------------------------------------- #
# Token válido
# --------------------------------------------------------------------------- #


def test_token_valido_passa_pela_autenticacao():
    """Não afirma 200 -- a rota sem banco real pode falhar adiante. Afirma que a
    autenticação deixou passar, que é o que este módulo controla.
    """
    resposta = _cliente().get("/api/v1/events", headers={"Authorization": f"Bearer {TOKEN}"})

    assert resposta.status_code not in (401, 403)


def test_bearer_minusculo_e_aceito():
    """RFC 7235: o nome do esquema é case-insensitive."""
    resposta = _cliente().get("/api/v1/events", headers={"Authorization": f"bearer {TOKEN}"})

    assert resposta.status_code not in (401, 403)


# --------------------------------------------------------------------------- #
# Rotas isentas
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("rota", ["/health/live", "/docs", "/openapi.json", "/favicon.ico"])
def test_rotas_publicas_dispensam_token(rota):
    """`/health/live` é a mais crítica das quatro: é a sonda do target group do
    ALB, que não carrega cabeçalho nenhum. Se ela exigisse token, todas as
    instâncias reprovariam e o Auto Scaling Group entraria em ciclo de
    substituição sem que houvesse nada errado com elas.
    """
    resposta = _cliente().get(rota)

    assert resposta.status_code not in (401, 403)


def test_health_ready_dispensa_token():
    """Também é sonda, e também é consultada sem cabeçalho."""
    resposta = _cliente().get("/health/ready")

    assert resposta.status_code not in (401, 403)


def test_preflight_do_cors_nao_e_barrado():
    """O preflight nunca carrega `Authorization`. Barrá-lo faria o navegador
    abortar a chamada real antes de tentá-la, e toda consulta autenticada do
    dashboard falharia por CORS -- com a causa aparecendo longe daqui.
    """
    resposta = _cliente().open(
        "/api/v1/events",
        method="OPTIONS",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )

    assert resposta.status_code not in (401, 403)
