"""Configuracao dos dois workers, toda vinda de variaveis de ambiente.

O ECS injeta essas variaveis pela task definition (ver infra/ecs.tf). Nada de
segredo entra aqui em arquivo: a DATABASE_URL vem do ambiente, montada pelo
Terraform a partir do Secrets Manager ou do tfvars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Limite duro do ReceiveMessage do SQS.
SQS_MAX_MESSAGES = 10


def _env_int(name: str, default: int) -> int:
    """Le uma variavel de ambiente convertendo-a para inteiro.

    Args:
        name (str): Nome da variavel de ambiente.
        default (int): Valor padrao caso a variavel esteja ausente.

    Returns:
        int: Valor inteiro obtido.

    Raises:
        ValueError: Se o valor lido nao puder ser convertido para int.
    """
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} precisa ser inteiro, recebi {raw!r}") from exc


@dataclass(frozen=True)
class Config:
    """Parametros de execucao comuns aos dois consumidores."""

    modo: str  # merge | event
    queue_url: str
    dlq_url: str
    database_url: str

    service_name: str = "argus-worker"
    metrics_namespace: str = "Argus/Ingestion"
    log_level: str = "INFO"

    # Consumo do SQS
    batch_size: int = SQS_MAX_MESSAGES
    wait_time_seconds: int = 20  # long polling: evita ReceiveMessage vazio em loop
    visibility_timeout_seconds: int = 180

    # Pool do PostgreSQL. Pequeno de proposito: um unico worker nao ganha nada
    # com conexoes extras (ele processa um lote por vez), e cada conexao ociosa
    # e um processo no servidor. O teto do RDS e compartilhado com a Lambda, que
    # escala sozinha.
    db_pool_min: int = 1
    db_pool_max: int = 4

    # Relogio de TV e notoriamente errado. Acima desse desvio o evento e marcado
    # com clock_skew=true (mas NUNCA descartado -- jogar fora perderia
    # justamente o aparelho com problema).
    max_clock_skew_days: int = 365

    heartbeat_path: str = "/tmp/argus-heartbeat"

    # Campos que esperamos em todo evento. Ausencia nao invalida o evento, so
    # incrementa a metrica EventsIncomplete: validacao vira observabilidade, nao
    # descarte.
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
    def from_env(cls, modo: str) -> Config:
        """Carrega e valida a configuracao a partir do ambiente.

        Args:
            modo (str): `merge` (change events) ou `event` (grain de sessao).

        Returns:
            Config: Instancia da configuracao populada.

        Raises:
            ValueError: Se o modo for desconhecido.
            RuntimeError: Se variaveis obrigatorias estiverem ausentes.
        """
        if modo not in ("merge", "event"):
            raise ValueError(f"modo desconhecido: {modo!r} (use merge ou event)")

        prefixo = "CHANGES" if modo == "merge" else "EVENTS"
        obrigatorias = (f"{prefixo}_QUEUE_URL", f"{prefixo}_DLQ_URL", "DATABASE_URL")
        faltando = [nome for nome in obrigatorias if not os.getenv(nome)]
        if faltando:
            raise RuntimeError(
                "variaveis de ambiente obrigatorias ausentes: " + ", ".join(faltando)
            )

        return cls(
            modo=modo,
            queue_url=os.environ[f"{prefixo}_QUEUE_URL"],
            dlq_url=os.environ[f"{prefixo}_DLQ_URL"],
            database_url=os.environ["DATABASE_URL"],
            service_name=os.getenv("SERVICE_NAME", f"argus-{modo}-worker"),
            metrics_namespace=os.getenv("METRICS_NAMESPACE", "Argus/Ingestion"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            batch_size=min(
                _env_int("SQS_BATCH_SIZE", SQS_MAX_MESSAGES), SQS_MAX_MESSAGES
            ),
            wait_time_seconds=_env_int("SQS_WAIT_TIME_SECONDS", 20),
            visibility_timeout_seconds=_env_int("SQS_VISIBILITY_TIMEOUT", 180),
            db_pool_min=_env_int("DB_POOL_MIN", 1),
            db_pool_max=_env_int("DB_POOL_MAX", 4),
            max_clock_skew_days=_env_int("MAX_CLOCK_SKEW_DAYS", 365),
            heartbeat_path=os.getenv("HEARTBEAT_PATH", "/tmp/argus-heartbeat"),
        )
