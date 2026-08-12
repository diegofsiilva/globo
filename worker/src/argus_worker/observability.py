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
    """Formata LogRecord como uma linha JSON, com os extras no mesmo nivel."""

    _RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
        "asctime",
        "message",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
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
    """Acumula metricas de um ciclo e emite um unico bloco EMF no flush."""

    def __init__(self, namespace: str, service_name: str) -> None:
        self._namespace = namespace
        self._service_name = service_name
        self._counts: dict[str, float] = {}
        self._units: dict[str, str] = {}

    def count(self, name: str, value: float = 1.0) -> None:
        self._counts[name] = self._counts.get(name, 0.0) + value
        self._units.setdefault(name, "Count")

    def duration_ms(self, name: str, value: float) -> None:
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
