"""Exceções de domínio da aplicação de telemetria."""


class TelemetryError(Exception):
    """Exceção base para erros de domínio previstos na aplicação."""


class ValidationError(TelemetryError):
    """Exceção de validação de dados de entrada do cliente."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        """Inicializa a exceção de validação.

        Args:
            message (str): Mensagem detalhada sobre o erro de validação.
            field (str | None): Campo associado à falha de validação, se aplicável.
        """
        super().__init__(message)
        self.field = field


class UnsupportedMediaTypeError(TelemetryError):
    """Exceção lançada quando o tipo de mídia ou Content-Type não é suportado."""


class EventNotFoundError(TelemetryError):
    """Exceção lançada quando um evento ou sessão solicitada não é encontrada."""


class ResourceNotFoundError(TelemetryError):
    """Recurso de leitura inexistente ou invisível para o cliente."""


class ConflictError(TelemetryError):
    """A operacao conflita com um registro idempotente anterior."""
