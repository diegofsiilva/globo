"""Lambda authorizer das APIs do Argus.

Authorizer do tipo REQUEST, payload 2.0, com resposta simples
(`{"isAuthorized": ...}`). O API Gateway o consulta antes de invocar a Lambda
de leitura ou de enfileirar um evento de ingestao, e guarda a decisao por cinco
minutos por token (`authorizer_result_ttl_in_seconds`).

Por que authorizer e nao API key: a chave de API do API Gateway existe para
medir e limitar consumo, e a propria AWS registra que ela **nao** e um mecanismo
de autorizacao -- a recomendacao e authorizer, IAM ou Cognito. Ver
https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html

## Como a decisao e tomada

Sao dois tokens aleatorios de 256 bits, um por audiencia:

| Audiencia   | Quem usa                              |
|-------------|---------------------------------------|
| `dashboard` | dashboard, Swagger, Postman de leitura |
| `ingest`    | simulador, replay de eventos, Postman de ingestao |

O Secrets Manager guarda **apenas o SHA-256** de cada um, em JSON
(`{"dashboard": "<hex>", "ingest": "<hex>"}`). O token em claro nunca e escrito
em lugar nenhum da AWS nem do repositorio: quem o gera e `make auth-rotate`,
que o imprime uma vez no terminal de quem rodou. SHA-256 simples basta aqui
porque o segredo tem 256 bits de entropia real -- um KDF lento protege senha
escolhida por humano, e nao existe dicionario para forcar um valor destes.

Cada API so aceita a sua audiencia (`AUDIENCIAS_POR_API`). O token de leitura
apresentado na API de ingestao e recusado, e vice-versa: sem isso, vazar o token
que fica no navegador do operador daria tambem o direito de injetar evento.

## O que vira 401 e o que vira 403

Sem o cabecalho `Authorization`, o API Gateway responde **401** sem sequer
invocar esta funcao -- e o comportamento do `identity_sources`. Com cabecalho
presente e token errado, esta funcao devolve `isAuthorized: false` e o gateway
responde **403**. A distincao e util no CloudWatch: 401 e cliente desconfigurado,
403 e tentativa com credencial invalida.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

import boto3

# `boto3` ja vem no runtime da Lambda, entao nao entra no zip. Vale para esta
# funcao, e nao para a API de leitura: la ele foi removido de proposito
# (backend/AGENTS.md, regra 5) porque a API nao fala com servico da AWS.
_secrets = boto3.client("secretsmanager")

logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

PREFIXO_BEARER = "bearer "

# Por quanto tempo o hash lido do Secrets Manager fica em memoria no container.
# Vale como teto de propagacao da rotacao: depois de `make auth-rotate`, o token
# antigo para de funcionar em, no maximo, este intervalo somado ao cache de
# decisao do proprio API Gateway.
TTL_CACHE_SEGUNDOS = 300

_cache: dict[str, Any] = {"hashes": None, "expira_em": 0.0}


def lambda_handler(event: dict, context: Any) -> dict:
    """Decide se a requisicao pode seguir para a integracao.

    Args:
        event (dict): Evento do API Gateway HTTP API, payload format 2.0.
        context (Any): Contexto de execucao da Lambda, nao utilizado.

    Returns:
        dict: `{"isAuthorized": bool}` e, quando autorizado, um `context` com a
            audiencia. O `context` chega a integracao em
            `requestContext.authorizer.lambda` -- e de la que o log estruturado
            da API le a audiencia, em vez de confiar num cabecalho que o
            proprio cliente poderia forjar.
    """
    audiencias = _audiencias_da_api(event)
    token = _token_do_cabecalho(event)

    if not token or not audiencias:
        # Sem detalhe do motivo na resposta, de proposito: quem esta tentando
        # adivinhar o token nao deve aprender se errou o formato ou o valor.
        logger.info(
            json.dumps(
                {
                    "event": "authorizer_deny",
                    "reason": "sem_token" if not token else "api_desconhecida",
                    "request_id": _request_id(event),
                }
            )
        )
        return {"isAuthorized": False}

    audiencia = _audiencia_do_token(token, audiencias)
    if audiencia is None:
        logger.info(
            json.dumps(
                {
                    "event": "authorizer_deny",
                    "reason": "token_invalido",
                    "request_id": _request_id(event),
                }
            )
        )
        return {"isAuthorized": False}

    logger.info(
        json.dumps(
            {
                "event": "authorizer_allow",
                "audience": audiencia,
                "request_id": _request_id(event),
            }
        )
    )
    return {"isAuthorized": True, "context": {"audience": audiencia}}


def _token_do_cabecalho(event: dict) -> str | None:
    """Extrai o token do cabecalho `Authorization: Bearer <token>`.

    Args:
        event (dict): Evento do API Gateway.

    Returns:
        str | None: O token, ou `None` quando o cabecalho falta ou nao usa o
            esquema Bearer.
    """
    cabecalhos = event.get("headers") or {}
    # O API Gateway ja entrega os nomes em minusculo no payload 2.0, mas a
    # varredura abaixo torna a funcao testavel com um dicionario escrito a mao.
    bruto = ""
    for nome, valor in cabecalhos.items():
        if nome.lower() == "authorization":
            bruto = valor or ""
            break

    if not bruto.lower().startswith(PREFIXO_BEARER):
        return None
    token = bruto[len(PREFIXO_BEARER) :].strip()
    return token or None


def _audiencias_da_api(event: dict) -> list[str]:
    """Descobre quais audiencias a API alvo aceita.

    Args:
        event (dict): Evento do API Gateway; o id da API sai do `routeArn`
            (`arn:aws:execute-api:regiao:conta:apiId/stage/METODO/rota`).

    Returns:
        list[str]: Audiencias aceitas por essa API, ou lista vazia quando a API
            nao esta no mapa -- o que resulta em negacao.
    """
    route_arn = event.get("routeArn") or ""
    partes = route_arn.split(":")
    api_id = partes[5].split("/")[0] if len(partes) > 5 else ""

    try:
        mapa = json.loads(os.environ.get("AUDIENCIAS_POR_API", "{}"))
    except json.JSONDecodeError:
        logger.error(json.dumps({"event": "config_invalida", "var": "AUDIENCIAS_POR_API"}))
        return []
    return list(mapa.get(api_id, []))


def _audiencia_do_token(token: str, audiencias: list[str]) -> str | None:
    """Compara o token com os hashes conhecidos, em tempo constante.

    Args:
        token (str): Token apresentado pelo cliente.
        audiencias (list[str]): Audiencias que a API alvo aceita.

    Returns:
        str | None: A audiencia correspondente, ou `None` se nenhum hash bate.
    """
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    hashes = _hashes_conhecidos()

    encontrada: str | None = None
    for audiencia in audiencias:
        esperado = hashes.get(audiencia)
        if not esperado:
            continue
        # `compare_digest` em vez de `==`: a comparacao ingenua sai no primeiro
        # byte diferente, e a diferenca de tempo entre "errou no primeiro
        # caractere" e "errou no ultimo" e mensuravel pela rede. O laco NAO da
        # `break` no acerto pelo mesmo motivo -- sair mais cedo revelaria a
        # posicao da audiencia que casou.
        if hmac.compare_digest(digest, esperado) and encontrada is None:
            encontrada = audiencia
    return encontrada


def _hashes_conhecidos() -> dict[str, str]:
    """Le os hashes do Secrets Manager, com cache curto em memoria.

    Sem o cache, cada decisao do authorizer viraria uma chamada ao Secrets
    Manager -- que e cobrada por requisicao e tem limite de throughput proprio.

    Returns:
        dict[str, str]: Audiencia -> SHA-256 do token, em hexadecimal
            minusculo. Vazio quando o segredo nao existe ou nao e JSON, caso em
            que nenhuma comparacao bate e tudo e negado.
    """
    agora = time.monotonic()
    if _cache["hashes"] is not None and agora < _cache["expira_em"]:
        return _cache["hashes"]

    try:
        resposta = _secrets.get_secret_value(SecretId=os.environ["SECRET_ID"])
        hashes = {
            str(audiencia): str(valor).lower()
            for audiencia, valor in json.loads(resposta["SecretString"]).items()
        }
    except Exception:  # noqa: BLE001 - qualquer falha aqui significa negar
        # Falha fechada: sem os hashes, nada e autorizado. O contrario
        # transformaria uma indisponibilidade do Secrets Manager em acesso
        # aberto ao banco.
        logger.exception(json.dumps({"event": "segredo_indisponivel"}))
        return {}

    _cache["hashes"] = hashes
    _cache["expira_em"] = agora + TTL_CACHE_SEGUNDOS
    return hashes


def _request_id(event: dict) -> str | None:
    """Devolve o `requestId` do API Gateway, para correlacionar com a API.

    Args:
        event (dict): Evento do API Gateway.

    Returns:
        str | None: O identificador da requisicao, quando presente.
    """
    contexto = event.get("requestContext") or {}
    return contexto.get("requestId")
