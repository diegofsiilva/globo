"""Logs estruturados e metricas CloudWatch via EMF.

Tudo sai em JSON no stdout. O awslogs driver do ECS entrega no CloudWatch Logs, e
o CloudWatch extrai as metricas dos blocos EMF sozinho -- nao ha chamada de
PutMetricData, entao emitir metrica aqui custa zero em API e em latencia.

Formato EMF: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any


class JsonFormatter(logging.Formatter):
    """Formata LogRecord como uma linha JSON, com os extras no mesmo nível."""

    _RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
        "asctime",
        "message",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        """Formata o registro de log em uma string JSON estruturada.

        Args:
            record (logging.LogRecord): Registro do log.

        Returns:
            str: String JSON com a linha de log.
        """
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
        }
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str, service_name: str) -> logging.Logger:
    """Configura a saída de logs estruturados em JSON para o stdout.

    Args:
        level (str): Nível mínimo do log ('INFO', 'DEBUG', 'WARNING', etc.).
        service_name (str): Nome do serviço para o logger retornado.

    Returns:
        logging.Logger: Instância do logger configurado.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))

    # boto3 em DEBUG despeja o corpo de toda request HTTP; nunca queremos isso.
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger(service_name)


class Metrics:
    """Acumula métricas de um ciclo e emite um único bloco EMF no flush."""

    def __init__(self, namespace: str, service_name: str) -> None:
        """Inicializa o gerenciador de métricas.

        Args:
            namespace (str): Namespace das métricas no CloudWatch.
            service_name (str): Nome do serviço para dimensão.
        """
        self._namespace = namespace
        self._service_name = service_name
        self._counts: dict[str, float] = {}
        self._units: dict[str, str] = {}

    def count(self, name: str, value: float = 1.0) -> None:
        """Incrementa um contador de métrica.

        Args:
            name (str): Nome da métrica.
            value (float, optional): Valor a incrementar. Padrão é 1.0.
        """
        self._counts[name] = self._counts.get(name, 0.0) + value
        self._units.setdefault(name, "Count")

    def duration_ms(self, name: str, value: float) -> None:
        """Registra uma métrica de duração em milissegundos.

        Args:
            name (str): Nome da métrica.
            value (float): Valor da duração em milissegundos.
        """
        self._counts[name] = value
        self._units[name] = "Milliseconds"

    def flush(self) -> None:
        """Imprime o bloco EMF e zera o acumulador."""
        if not self._counts:
            return

        document: dict[str, Any] = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self._namespace,
                        "Dimensions": [["Service"]],
                        "Metrics": [
                            {"Name": name, "Unit": self._units[name]}
                            for name in self._counts
                        ],
                    }
                ],
            },
            "Service": self._service_name,
            **self._counts,
        }
        # EMF precisa ir cru no stdout, sem o envelope do JsonFormatter.
        sys.stdout.write(json.dumps(document, default=str) + "\n")
        sys.stdout.flush()

        self._counts.clear()
        self._units.clear()
