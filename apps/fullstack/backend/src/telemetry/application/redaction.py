"""Remocao de dado pessoal na saida da API (RNF10).

A logica de allowlist de headers, saneamento de URL e hash de identificador
veio da camada de ingestao original, mas o momento de aplica-la mudou.

O motivo e concreto: a ingestao deste projeto e o pipeline
API Gateway -> SQS -> worker, e o worker grava o evento como o aparelho
enviou, sem transformar. Entao o DynamoDB tem `user_id` em claro e o header
`authorization` dentro de `request_headers`. Se a redacao ficasse so na
entrada, ela nunca rodaria -- e a API serviria o dado cru para o dashboard.

Redigir na saida tambem preserva a investigacao: o dado bruto continua no
banco para quem tiver acesso direto e justificativa, e o que trafega para a
tela e a versao reduzida.
"""

import hashlib
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Headers que podem aparecer no dashboard. Allowlist e nao blocklist de
# proposito: header novo no app entra como oculto ate alguem decidir o
# contrario, em vez de vazar por padrao.
SAFE_REQUEST_HEADERS = frozenset(
    {
        "accept",
        "content-type",
        "x-client-version",
        "x-platform-id",
        "x-device-id",
        "x-tenant-id",
        "x-country-code",
    }
)

# Chaves de query string que carregam credencial ou identificador.
SENSITIVE_QUERY_KEYS = frozenset({"access_token", "authorization", "token", "user_id"})

# Campos do evento que nunca saem da API, em nenhuma forma.
DROPPED_ATTRIBUTES = frozenset({"authorization", "response_headers"})

# Valor que o proprio export do parceiro usa para campo ja mascarado.
MASKED = "***"


def hash_user_id(user_id: str | None, salt: str) -> str | None:
    """Identificador estável e não reversível.

    O salt impede que alguém com a tabela de hashes cruze o resultado com uma
    lista conhecida de user_ids. Estável porque o dashboard precisa agrupar
    eventos do mesmo usuário sem saber quem ele é.

    Args:
        user_id (str | None): Identificador do usuário em claro.
        salt (str): Sal de segurança configurado para desidentificação.

    Returns:
        str | None: SHA-256 truncado em 32 caracteres hexadecimais, ou None se
            o valor estiver ausente ou já mascarado.
    """
    if not user_id or user_id == MASKED:
        return None
    return hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:32]


def sanitize_url(url: Any) -> str | None:
    """Remove credencial e identificador da query string, preservando a rota.

    Args:
        url (Any): URL original a ser higienizada.

    Returns:
        str | None: URL sem os parâmetros sensíveis, com esquema, host e path
            intactos, ou None se a entrada for vazia.
    """
    if not url:
        return None
    text = str(url)
    parts = urlsplit(text)
    if not parts.query:
        return text
    safe = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in SENSITIVE_QUERY_KEYS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe), ""))


def redact_headers(headers: Any) -> dict[str, Any]:
    """Filtra cabeçalhos HTTP mantendo apenas os presentes na allowlist de cabeçalhos seguros.

    Args:
        headers (Any): Dicionário de cabeçalhos HTTP.

    Returns:
        dict[str, Any]: Dicionário filtrado apenas com cabeçalhos permitidos.
    """
    if not isinstance(headers, dict):
        return {}
    return {
        str(key).lower(): value
        for key, value in headers.items()
        if str(key).lower() in SAFE_REQUEST_HEADERS
    }


def redact_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """Aplica a redação no bloco de campos específicos do tipo de evento.

    Args:
        attributes (dict[str, Any]): Dicionário de atributos do evento.

    Returns:
        dict[str, Any]: Atributos com os campos sensíveis removidos ou mascarados.
    """
    clean: dict[str, Any] = {}
    for key, value in attributes.items():
        lowered = key.lower()
        if lowered in DROPPED_ATTRIBUTES:
            continue
        if lowered == "request_headers":
            headers = redact_headers(value)
            if headers:
                clean[key] = headers
            continue
        if lowered == "request_url":
            url = sanitize_url(value)
            if url:
                clean[key] = url
            continue
        clean[key] = value
    return clean
