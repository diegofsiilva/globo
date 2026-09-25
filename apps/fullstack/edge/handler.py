"""Entrada HTTPS do dashboard com retorno automatico ao S3 e a API Lambda.

O API Gateway fornece o dominio HTTPS sem exigir dominio proprio. A Lambda
encaminha a requisicao ao ALB interno quando ele responde. Se o Ingress ou o
cluster falha, arquivos estaticos saem do S3 e consultas saem da API Lambda.
O token Bearer nunca e gravado em log ou em resposta de erro.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_HOST: str = ""
_HOST_EXPIRA: float = 0.0
_CABECALHOS_RESPOSTA = {
    "cache-control",
    "content-encoding",
    "content-language",
    "content-type",
    "etag",
    "expires",
    "last-modified",
    "location",
    "x-request-id",
}
_CABECALHOS_PEDIDO = {
    "accept",
    "authorization",
    "content-type",
    "if-modified-since",
    "if-none-match",
    "user-agent",
}


def _cliente(servico: str) -> Any:
    """Cria um cliente AWS somente quando a operacao precisa dele.

    Args:
        servico: Nome do servico AWS.

    Returns:
        Cliente boto3 do servico pedido.
    """
    import boto3

    return boto3.client(servico)


def _host_primario() -> str:
    """Le o hostname do ALB interno, com cache curto para troca operacional.

    Returns:
        Hostname validado, ou string vazia quando o cluster esta desligado.
    """
    global _HOST, _HOST_EXPIRA
    if time.monotonic() < _HOST_EXPIRA:
        return _HOST
    _HOST_EXPIRA = time.monotonic() + 10
    try:
        valor = (
            _cliente("ssm")
            .get_parameter(Name=os.environ["PRIMARY_HOST_PARAMETER"])["Parameter"][
                "Value"
            ]
            .strip()
        )
    except Exception:  # noqa: BLE001 - SSM fora do ar aciona a contingencia
        _HOST = ""
        return _HOST
    # O parametro e atualizado pelo Makefile. Validar o sufixo impede que uma
    # configuracao errada encaminhe o Bearer a um host arbitrario.
    _HOST = (
        valor
        if valor.startswith("internal-")
        and valor.endswith(".elb.amazonaws.com")
        and ":" not in valor
        and "/" not in valor
        else ""
    )
    return _HOST


def _pedido(evento: dict) -> tuple[str, str, bytes | None, dict[str, str]]:
    """Extrai metodo, caminho, corpo e cabecalhos do payload HTTP API v2.

    Args:
        evento: Evento recebido do API Gateway.

    Returns:
        Quatro valores normalizados para o proxy HTTP.
    """
    metodo = evento.get("requestContext", {}).get("http", {}).get("method", "GET")
    caminho = evento.get("rawPath", "/") or "/"
    consulta = evento.get("rawQueryString", "")
    if consulta:
        caminho += "?" + consulta
    corpo = evento.get("body")
    if corpo is not None:
        corpo = (
            base64.b64decode(corpo) if evento.get("isBase64Encoded") else corpo.encode()
        )
    cabecalhos = {
        nome.lower(): valor
        for nome, valor in (evento.get("headers") or {}).items()
        if nome.lower() in _CABECALHOS_PEDIDO
    }
    # O nginx pode comprimir a resposta, mas o API Gateway so precisa receber
    # os bytes originais. Pedir identity evita encaminhar um Content-Encoding
    # desatualizado quando o gateway serializa a resposta.
    cabecalhos["accept-encoding"] = "identity"
    return metodo, caminho, corpo, cabecalhos


def _requisitar(
    url: str,
    metodo: str,
    corpo: bytes | None,
    cabecalhos: dict[str, str],
    timeout: int = 12,
) -> dict:
    """Encaminha uma requisicao e preserva status, corpo e cabecalhos uteis.

    Args:
        url: Destino HTTP interno ou HTTPS de contingencia.
        metodo: Metodo HTTP original.
        corpo: Corpo original, quando presente.
        cabecalhos: Cabecalhos permitidos para o destino.
        timeout: Prazo em segundos para a origem responder.

    Returns:
        Resposta no formato de proxy HTTP API v2.

    Raises:
        urllib.error.URLError: Quando o destino nao responde.
    """
    pedido = urllib.request.Request(url, data=corpo, headers=cabecalhos, method=metodo)
    try:
        resposta = urllib.request.urlopen(pedido, timeout=timeout)
    except urllib.error.HTTPError as erro:
        resposta = erro
    with resposta:
        bruto = resposta.read()
        return {
            "statusCode": resposta.status,
            "headers": {
                nome: valor
                for nome, valor in resposta.headers.items()
                if nome.lower() in _CABECALHOS_RESPOSTA
            },
            "body": base64.b64encode(bruto).decode(),
            "isBase64Encoded": True,
        }


def _chave_s3(caminho: str) -> str | None:
    """Converte uma rota do export estatico em chave S3 sem permitir travessia.

    Args:
        caminho: Caminho da requisicao, sem query string.

    Returns:
        Chave do objeto ou None para caminho invalido.
    """
    partes = urllib.parse.unquote(caminho).replace("\\", "/").split("/")
    if any(parte in (".", "..") for parte in partes):
        return None
    chave = "/".join(parte for parte in partes if parte)
    if not chave or caminho.endswith("/"):
        return f"{chave + '/' if chave else ''}index.html"
    if "." not in chave.rsplit("/", 1)[-1]:
        return f"{chave}/index.html"
    return chave


def _estatico_s3(caminho: str, metodo: str) -> dict:
    """Serve o export estatico pelo S3 quando o Ingress nao responde.

    Args:
        caminho: Caminho da pagina ou do asset.
        metodo: GET ou HEAD.

    Returns:
        Resposta HTTP API com tipo MIME e corpo corretos.
    """
    chave = _chave_s3(caminho)
    if not chave:
        return {"statusCode": 400, "body": "Caminho invalido"}
    try:
        objeto = _cliente("s3").get_object(
            Bucket=os.environ["FRONTEND_BUCKET"], Key=chave
        )
        bruto = objeto["Body"].read() if metodo == "GET" else b""
    except Exception:  # noqa: BLE001 - objeto ausente ou S3 indisponivel
        return {"statusCode": 404, "body": "Pagina indisponivel"}
    tipo = (
        objeto.get("ContentType")
        or mimetypes.guess_type(chave)[0]
        or "application/octet-stream"
    )
    return {
        "statusCode": 200,
        "headers": {
            "content-type": tipo,
            "cache-control": "public, max-age=31536000, immutable"
            if chave.startswith("_next/static/")
            else "no-cache",
        },
        "body": base64.b64encode(bruto).decode(),
        "isBase64Encoded": True,
    }


def lambda_handler(event: dict, context: Any) -> dict:
    """Tenta o EKS e comuta automaticamente para as origens de contingencia.

    Args:
        event: Evento HTTP API v2.
        context: Contexto Lambda, nao utilizado.

    Returns:
        Resposta HTTP API v2 sem expor endpoints nem tokens em erros.
    """
    del context
    metodo, caminho, corpo, cabecalhos = _pedido(event)
    rota = caminho.split("?", 1)[0]
    api = (
        rota == "/api"
        or rota.startswith("/api/")
        or rota == "/health"
        or rota.startswith("/health/")
    )
    host = _host_primario()
    if host:
        try:
            resposta = _requisitar(
                f"http://{host}{caminho}",
                metodo,
                corpo,
                cabecalhos,
                timeout=12 if api else 3,
            )
            if resposta["statusCode"] not in (502, 503, 504):
                return resposta
        except (TimeoutError, urllib.error.URLError, OSError):
            pass
    if api:
        # Uma resposta perdida apos uma escrita pode significar que o backend
        # ja gravou os dados. Repetir POST em outra origem criaria duplicatas.
        if host and metodo not in ("GET", "HEAD"):
            return {
                "statusCode": 503,
                "body": json.dumps({"error": "leitura indisponivel"}),
            }
        try:
            destino = os.environ["READ_API_URL"].rstrip("/") + caminho
            return _requisitar(destino, metodo, corpo, cabecalhos, timeout=15)
        except (TimeoutError, urllib.error.URLError, OSError):
            return {
                "statusCode": 503,
                "body": json.dumps({"error": "leitura indisponivel"}),
            }
    if metodo not in ("GET", "HEAD"):
        return {"statusCode": 405, "body": "Metodo nao permitido"}
    return _estatico_s3(rota, metodo)
