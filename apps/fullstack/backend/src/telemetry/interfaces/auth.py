"""Validação do token Bearer dentro da aplicação Flask.

Até a v3 esta checagem não existia aqui: quem a fazia era o Lambda authorizer
(`authorizer/handler.py`), consultado pelo API Gateway antes de invocar a
Lambda. A aplicação recebia apenas requisições já autorizadas e podia ignorar o
assunto.

Ao mover a API de leitura para instâncias EC2 atrás de um Application Load
Balancer, esse degrau desaparece — um ALB não tem authorizer. Sem o que está
neste módulo, tirar o API Gateway do caminho deixaria toda a API aberta.

## O que chega na instância

O **hash** do token, nunca o token. `DASHBOARD_TOKEN_SHA256` é lido do Secrets
Manager pelo `user_data` no boot da instância (ver `infra/asg.tf`) e injetado
como variável de ambiente do container. A aplicação não fala com a AWS — `boto3`
foi removido dela de propósito (ver `backend/AGENTS.md`, regra 5) — então quem
consulta o segredo é o script de boot, e não este código.

Consequência assumida: rotacionar o token com `make auth-rotate` exige um
`start-instance-refresh` no Auto Scaling Group, porque o hash foi congelado no
boot. Instâncias antigas continuam aceitando o token antigo até serem
substituídas.

## 401 e 403

A distinção é a mesma que o authorizer estabelecia, e vale preservá-la porque é
o que separa cliente desconfigurado de tentativa com credencial inválida quando
se olha o CloudWatch:

- **401** — cabeçalho `Authorization` ausente ou malformado.
- **403** — cabeçalho presente, token errado.

## Comparação

SHA-256 simples, sem KDF, e a comparação por `hmac.compare_digest`. O token tem
256 bits de entropia real: não existe dicionário para forçá-lo, e um KDF lento
protegeria contra um ataque que não se aplica. `compare_digest` evita que o
tempo da comparação revele quantos bytes iniciais estavam certos.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from flask import Flask, request

from telemetry.interfaces.openapi import ROTAS_PUBLICAS

PREFIXO_BEARER = "bearer "


def hash_do_token(token: str) -> str:
    """Devolve o SHA-256 hexadecimal de um token.

    Mesma função do `authorizer/handler.py`. Duplicada e não importada porque o
    authorizer é empacotado num zip próprio, sem dependência do backend — e são
    três linhas cuja divergência quebraria a autenticação de forma visível no
    primeiro teste.

    Args:
        token (str): Token em claro, como veio do cabeçalho.

    Returns:
        str: Digest SHA-256 em hexadecimal minúsculo.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_do_cabecalho(valor: str | None) -> str | None:
    """Extrai o token de um cabeçalho `Authorization`.

    Args:
        valor (str | None): Conteúdo bruto do cabeçalho, ou `None` se ausente.

    Returns:
        str | None: O token sem o prefixo `Bearer`, ou `None` quando o cabeçalho
            está ausente, não usa o esquema Bearer ou vem sem valor depois do
            prefixo.
    """
    if not valor:
        return None

    # Comparação insensível a caixa: a RFC 7235 define o esquema como
    # case-insensitive, e cliente que manda "bearer" minúsculo é comum.
    if not valor.lower().startswith(PREFIXO_BEARER):
        return None

    token = valor[len(PREFIXO_BEARER) :].strip()
    return token or None


def rota_publica(caminho: str) -> bool:
    """Diz se um caminho dispensa autenticação.

    A lista vem de `ROTAS_PUBLICAS`, em `interfaces/openapi.py`, que é a mesma
    fonte usada para marcar a especificação OpenAPI e para as rotas com
    `authorization_type = "NONE"` em `infra/auth.tf`. Reaproveitar em vez de
    redefinir é o que impede os três lugares de divergirem.

    `/health/ready` **não** é pública ali, mas é tratada como pública aqui: o
    health check do target group do ALB não carrega cabeçalho `Authorization`, e
    uma sonda que devolve 401 reprova a instância e a coloca em ciclo de
    substituição. O que ela revela é se o banco responde, e não dado nenhum.

    Args:
        caminho (str): `request.path` da requisição.

    Returns:
        bool: `True` quando a rota pode ser servida sem token.
    """
    if caminho in ROTAS_PUBLICAS or caminho == "/health/ready":
        return True

    # O favicon é pedido pelo navegador por navegação, sem cabeçalho nenhum, e
    # responder 401 a ele só suja o log de acesso.
    return caminho == "/favicon.ico"


def register_auth(app: Flask) -> None:
    """Registra a checagem de token Bearer, quando ela estiver ligada.

    Fica **desligada por padrão** e só ativa com `AUTH_REQUIRED=1`. O motivo é
    que o desenvolvimento local, os testes e o `make test-frontend-e2e` sobem a
    aplicação sem segredo nenhum; exigir token por padrão obrigaria todos eles a
    carregar um. Na AWS, quem liga a variável é o `user_data` do launch template.

    Se `AUTH_REQUIRED=1` for pedido sem `DASHBOARD_TOKEN_SHA256`, a aplicação
    **recusa a subir**. Falha fechada e barulhenta: o modo de falha alternativo
    seria uma API que se acha protegida e não está, e que ninguém descobre até
    alguém varrer a internet.

    Args:
        app (Flask): Aplicação onde o `before_request` será registrado.

    Raises:
        RuntimeError: Se a checagem for exigida sem o hash do token configurado.
    """
    exigir = str(app.config.get("AUTH_REQUIRED", os.getenv("AUTH_REQUIRED", "0")))
    if exigir not in {"1", "true", "True"}:
        return

    esperado = str(
        app.config.get("DASHBOARD_TOKEN_SHA256", os.getenv("DASHBOARD_TOKEN_SHA256", ""))
    ).strip()

    if not esperado:
        raise RuntimeError(
            "AUTH_REQUIRED=1 sem DASHBOARD_TOKEN_SHA256. A API subiria sem "
            "autenticacao nenhuma achando que esta protegida. O hash e lido do "
            "Secrets Manager pelo user_data da instancia -- ver infra/asg.tf."
        )

    @app.before_request
    def verificar_token():  # noqa: ANN202 -- handler do Flask, retorno é resposta ou None
        """Barra a requisição quando o token não confere.

        Returns:
            Response | None: `None` deixa a requisição seguir para a rota;
                uma resposta RFC 7807 com 401 ou 403 a interrompe.
        """
        # O preflight do CORS nunca carrega `Authorization`. Barrá-lo faria o
        # navegador abortar a chamada real antes de tentá-la, e toda consulta
        # autenticada do dashboard falharia por CORS -- com a causa aparecendo
        # como erro de origem, longe daqui.
        if request.method == "OPTIONS":
            return None

        if rota_publica(request.path):
            return None

        # Importado aqui e não no topo: `app.problem` vive em `telemetry.app`,
        # que importa este módulo indiretamente pela factory. No topo, os dois
        # se importariam em círculo.
        from telemetry.app import problem

        token = _token_do_cabecalho(request.headers.get("Authorization"))

        if token is None:
            return problem(
                401,
                "Nao autenticado",
                "Envie o cabecalho `Authorization: Bearer <token>`.",
            )

        if not hmac.compare_digest(hash_do_token(token), esperado):
            return problem(403, "Token invalido", "O token apresentado nao e aceito.")

        return None
