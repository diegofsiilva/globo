class TelemetryError(Exception):
    """Base exception for expected application errors."""


class ValidationError(TelemetryError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class UnsupportedMediaTypeError(TelemetryError):
    pass
