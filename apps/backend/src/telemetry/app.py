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
from telemetry.infrastructure.database import build_repository
from telemetry.interfaces.http import api, health


def create_app(config: dict[str, Any] | type[Config] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        if isinstance(config, dict):
            app.config.from_mapping(config)
        else:
            app.config.from_object(config)

    app.extensions["event_repository"] = build_repository(app.config["DATABASE_URL"])
    app.register_blueprint(api)
    app.register_blueprint(health)
    register_error_handlers(app)
    return app


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ValidationError)
    def handle_validation(error: ValidationError):
        return problem(422, "Validation error", str(error), field=error.field)

    @app.errorhandler(UnsupportedMediaTypeError)
    def handle_media_type(error: UnsupportedMediaTypeError):
        return problem(415, "Unsupported media type", str(error))

    @app.errorhandler(EventNotFoundError)
    def handle_not_found(error: EventNotFoundError):
        return problem(404, "Event not found", str(error))

    @app.errorhandler(BadRequest)
    def handle_bad_request(error: BadRequest):
        return problem(400, "Bad request", "Corpo da requisicao invalido")

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(error: RequestEntityTooLarge):
        return problem(413, "Payload too large", "O corpo excede o limite configurado")

    @app.errorhandler(HTTPException)
    def handle_http(error: HTTPException):
        return problem(error.code or 500, error.name, error.description)

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        app.logger.exception("unexpected_error", extra={"path": request.path})
        return problem(500, "Internal server error", "Erro interno inesperado")


def problem(status: int, title: str, detail: str, **extra: Any):
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
