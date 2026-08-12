"""Configuracao do worker, toda vinda de variaveis de ambiente.

O ECS injeta essas variaveis pela task definition (ver infra/ecs.tf). Nada de
segredo entra aqui: credenciais vem da task role via metadata endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Limite duro do BatchWriteItem do DynamoDB.
DYNAMO_MAX_BATCH = 25

# Limite duro do ReceiveMessage do SQS.
SQS_MAX_MESSAGES = 10


def _env_int(name: str, default: int) -> int:
    """Lê uma variável de ambiente convertendo-a para número inteiro com valor padrão.

    Args:
        name (str): Nome da variável de ambiente.
        default (int): Valor padrão caso a variável esteja ausente.

    Returns:
        int: Valor inteiro obtido.

    Raises:
        ValueError: Se o valor lido não puder ser convertido para int.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} precisa ser inteiro, recebi {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    """Lê uma variável de ambiente convertendo-a para booleano.

    Args:
        name (str): Nome da variável de ambiente.
        default (bool): Valor padrão se ausente.

    Returns:
        bool: Valor booleano parseado.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    """Parâmetros de execução e configuração do worker de ingestão."""

    queue_url: str
    dlq_url: str
    table_name: str
    region: str

    service_name: str = "argus-events-worker"
    metrics_namespace: str = "Argus/Ingestion"
    log_level: str = "INFO"

    # Consumo do SQS
    batch_size: int = SQS_MAX_MESSAGES
    wait_time_seconds: int = 20  # long polling: evita ReceiveMessage vazio em loop
    visibility_timeout_seconds: int = 60

    # Escrita no DynamoDB
    write_max_retries: int = 5
    gsi1_shards: int = 10

    # Retencao: TTL contado a partir da ingestao, nao do horario do evento, para
    # que replay de dado historico nao expire no instante em que entra.
    retention_days: int = 90

    # Relogio de TV e notoriamente errado. Acima desse desvio o evento e marcado
    # com clock_skew=true (mas nunca descartado).
    max_clock_skew_days: int = 365

    heartbeat_path: str = "/tmp/argus-worker-heartbeat"

    # Campos que esperamos em todo evento. Ausencia nao invalida o evento, so
    # incrementa a metrica EventsIncomplete.
    recommended_fields: tuple[str, ...] = field(
        default=(
            "app_bucket",
            "app_env",
            "app_target",
            "app_version",
            "device_manufacturer",
            "device_model",
            "device_os",
        )
    )

    @classmethod
    def from_env(cls) -> Config:
        """Carrega e valida as configurações do worker a partir das variáveis de ambiente.

        Returns:
            Config: Instância da configuração populada.

        Raises:
            RuntimeError: Se variáveis obrigatórias estiverem ausentes.
        """
        missing = [
            name
            for name in ("EVENTS_QUEUE_URL", "EVENTS_DLQ_URL", "EVENTS_TABLE_NAME")
            if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError(
                "variaveis de ambiente obrigatorias ausentes: " + ", ".join(missing)
            )

        return cls(
            queue_url=os.environ["EVENTS_QUEUE_URL"],
            dlq_url=os.environ["EVENTS_DLQ_URL"],
            table_name=os.environ["EVENTS_TABLE_NAME"],
            region=os.getenv("AWS_REGION", "us-east-1"),
            service_name=os.getenv("SERVICE_NAME", "argus-events-worker"),
            metrics_namespace=os.getenv("METRICS_NAMESPACE", "Argus/Ingestion"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            batch_size=min(
                _env_int("SQS_BATCH_SIZE", SQS_MAX_MESSAGES), SQS_MAX_MESSAGES
            ),
            wait_time_seconds=_env_int("SQS_WAIT_TIME_SECONDS", 20),
            visibility_timeout_seconds=_env_int("SQS_VISIBILITY_TIMEOUT", 60),
            write_max_retries=_env_int("DYNAMO_WRITE_MAX_RETRIES", 5),
            gsi1_shards=max(1, _env_int("GSI1_SHARDS", 10)),
            retention_days=_env_int("RETENTION_DAYS", 90),
            max_clock_skew_days=_env_int("MAX_CLOCK_SKEW_DAYS", 365),
            heartbeat_path=os.getenv("HEARTBEAT_PATH", "/tmp/argus-worker-heartbeat"),
        )
