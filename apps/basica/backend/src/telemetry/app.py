"""Factory de criação da aplicação Flask e manipuladores globais de requisições e erros."""

import logging
from typing import Any

from flask import Flask, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge

from telemetry.config import Config
from telemetry.domain.exceptions import (
    EventNotFoundError,
    UnsupportedMediaTypeError,
    ValidationError,
)
from telemetry.infrastructure.gold import GoldRepository
from telemetry.infrastructure.postgres import PostgresEventRepository, build_pool
from telemetry.infrastructure.signals import SignalsRepository
from telemetry.interfaces.http import api, health
from telemetry.interfaces.signals_http import signals_api


def create_app(
    config: dict[str, Any] | type[Config] | None = None,
    *,
    repository: Any = None,
    gold: Any = None,
    signals: Any = None,
) -> Flask:
    """Monta a aplicação.

    Args:
        config (dict[str, Any] | type[Config] | None): Configurações a aplicar
            por cima do `Config` padrão.
        repository (Any, optional): Permite injetar um adaptador pronto -- é o
            que os testes usam para apontar a API para outro banco sem passar
            por variável de ambiente.
        gold (Any, optional): Idem, para o repositório da camada gold.
        signals (Any, optional): Idem, para o repositório de `/api/v1/signals`.
            No ramo sem injeção (abaixo) é construído a partir do mesmo pool
            automaticamente; se `repository`/`gold` forem injetados sem
            `signals`, a extensão fica ausente e a rota de sinais não deve
            ser exercida por esse teste.

    Returns:
        Flask: Instância da aplicação Flask pronta para execução.
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        if isinstance(config, dict):
            app.config.from_mapping(config)
        else:
            app.config.from_object(config)

    if repository is not None and gold is not None:
        app.extensions["event_repository"] = repository
        app.extensions["gold_repository"] = gold
        if signals is not None:
            app.extensions["signals_repository"] = signals
    else:
        url = app.config.get("DATABASE_URL")
        if not url:
            raise RuntimeError(
                "DATABASE_URL nao definida. A API le do PostgreSQL desde a v3; "
                "veja `terraform output database_url_hint`."
            )
        # UM pool para os dois repositorios. Cada execucao concorrente da Lambda
        # e um processo proprio, e dois pools por processo dobrariam o consumo
        # de conexao do RDS sem dobrar a concorrencia real.
        pool = build_pool(url)
        app.extensions["db_pool"] = pool
        app.extensions["event_repository"] = repository or PostgresEventRepository(
            pool,
            user_id_hash_salt=app.config["USER_ID_HASH_SALT"],
            default_window_hours=app.config["DEFAULT_WINDOW_HOURS"],
            max_items_scanned=app.config["MAX_ITEMS_SCANNED"],
        )
        app.extensions["gold_repository"] = gold or GoldRepository(
            pool, max_points=app.config["MAX_ITEMS_SCANNED"]
        )
        app.extensions["signals_repository"] = signals or SignalsRepository(pool)
    app.register_blueprint(api)
    app.register_blueprint(health)
    app.register_blueprint(signals_api)
    register_cors(app)
    register_error_handlers(app)
    return app


def register_cors(app: Flask) -> None:
    """CORS manual, sem dependência extra.

    A dashboard é um site estático (Next com output: export) servido de outra
    origem, então o navegador exige estes cabeçalhos. Escrito à mão porque são
    poucas linhas e cada dependência a menos é um pacote a menos para caber no
    limite de tamanho da Lambda.

    Args:
        app (Flask): Aplicação Flask onde o handler de CORS será registrado.
    """
    origins = [
        origin.strip()
        for origin in str(app.config.get("CORS_ORIGINS", "*")).split(",")
        if origin.strip()
    ]

    @app.after_request
    def apply_cors(response):
        """Acrescenta os cabeçalhos de CORS a toda resposta que sai da API."""
        requested = request.headers.get("Origin")
        if "*" in origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif requested and requested in origins:
            response.headers["Access-Control-Allow-Origin"] = requested
            response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Max-Age"] = "300"
        return response


def register_error_handlers(app: Flask) -> None:
    """Registra manipuladores globais de exceção para resposta Problem Details (RFC 7807).

    Args:
        app (Flask): Aplicação Flask para o registro dos errorhandlers.
    """

    @app.errorhandler(ValidationError)
    def handle_validation(error: ValidationError):
        """Filtro ou payload inválido -> 422, apontando o campo culpado."""
        return problem(422, "Validation error", str(error), field=error.field)

    @app.errorhandler(UnsupportedMediaTypeError)
    def handle_media_type(error: UnsupportedMediaTypeError):
        """Content-Type que a API não aceita -> 415."""
        return problem(415, "Unsupported media type", str(error))

    @app.errorhandler(EventNotFoundError)
    def handle_not_found(error: EventNotFoundError):
        """Evento ou sessão inexistente -> 404."""
        return problem(404, "Event not found", str(error))

    @app.errorhandler(BadRequest)
    def handle_bad_request(error: BadRequest):
        """Corpo malformado detectado pelo Werkzeug -> 400."""
        return problem(400, "Bad request", "Corpo da requisicao invalido")

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(error: RequestEntityTooLarge):
        """Corpo acima de MAX_CONTENT_LENGTH -> 413."""
        return problem(413, "Payload too large", "O corpo excede o limite configurado")

    @app.errorhandler(HTTPException)
    def handle_http(error: HTTPException):
        """Rede de segurança das demais HTTPException, preservando o status original."""
        return problem(error.code or 500, error.name, error.description)

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        """Último recurso: registra o traceback e devolve 500 sem vazar detalhe interno."""
        app.logger.exception("unexpected_error", extra={"path": request.path})
        return problem(500, "Internal server error", "Erro interno inesperado")


def problem(status: int, title: str, detail: str, **extra: Any):
    """Gera uma resposta padronizada de erro seguindo a RFC 7807 (Problem Details).

    Args:
        status (int): Código de status HTTP do erro.
        title (str): Título legível do erro.
        detail (str): Descrição detalhada do erro.
        **extra (Any): Campos adicionais a serem incorporados no JSON de resposta.

    Returns:
        Response: Objeto de resposta JSON do Flask com Content-Type 'application/problem+json'.
    """
    payload = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.path,
        **{key: value for key, value in extra.items() if value is not None},
    }
    response = jsonify(payload)
    response.status_code = status
    response.content_type = "application/problem+json"
    return response


logging.basicConfig(level=logging.INFO)
