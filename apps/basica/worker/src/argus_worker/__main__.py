"""Entrypoint do container. Uma imagem, dois workers.

Uso:
    python -m argus_worker merge   # change events -> change_log -> MERGE
    python -m argus_worker event   # grain de sessao -> bronze.event

O modo vem do `command` da task definition (ver infra/ecs.tf). Os dois
consumidores compartilham o laco de SQS, a observabilidade e o pool de conexao,
e diferem apenas no que validam e onde gravam -- por isso uma imagem so, com
dois pontos de entrada, em vez de duas imagens 95% identicas.
"""

from __future__ import annotations

import sys

import boto3
from argus_common import Database, Heartbeat, Metrics, ShutdownSignal, configure_logging
from botocore.config import Config as BotoConfig

from .config import Config
from .consumer import ChangeConsumer, EventConsumer
from .repository import ChangeRepository, EventRepository

MODOS = ("merge", "event")


def build_boto_config(config: Config) -> BotoConfig:
    """Monta a configuracao dos clientes AWS.

    Args:
        config (Config): Configuracao do worker.

    Returns:
        BotoConfig: Configuracao do boto3.
    """
    return BotoConfig(
        retries={"max_attempts": 5, "mode": "adaptive"},
        # Precisa ser maior que o long polling do SQS, senao todo receive vazio
        # estoura timeout.
        read_timeout=config.wait_time_seconds + 10,
        connect_timeout=5,
        max_pool_connections=25,
    )


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada.

    Args:
        argv (list[str] | None): Argumentos da linha de comando.

    Returns:
        int: 0 em sucesso, 1 em falha.
    """
    args = sys.argv[1:] if argv is None else argv
    modo = args[0] if args else ""
    if modo not in MODOS:
        print(
            f"uso: python -m argus_worker {{{'|'.join(MODOS)}}}\n     recebi {modo!r}",
            file=sys.stderr,
        )
        return 1

    try:
        config = Config.from_env(modo)
    except (RuntimeError, ValueError) as exc:
        print(f"erro de configuracao: {exc}", file=sys.stderr)
        return 1

    log = configure_logging(config.log_level, config.service_name)

    db = None
    try:
        db = Database(
            config.database_url,
            min_size=config.db_pool_min,
            max_size=config.db_pool_max,
            application_name=config.service_name,
        )

        sqs = boto3.session.Session().client("sqs", config=build_boto_config(config))
        comum = {
            "config": config,
            "sqs_client": sqs,
            "metrics": Metrics(config.metrics_namespace, config.service_name),
            "heartbeat": Heartbeat(config.heartbeat_path),
            "shutdown": ShutdownSignal(),
        }

        if modo == "merge":
            consumer = ChangeConsumer(repository=ChangeRepository(db), **comum)
        else:
            consumer = EventConsumer(repository=EventRepository(db), **comum)

        consumer.run()
    except Exception:
        log.exception("worker abortou")
        return 1
    finally:
        if db is not None:
            db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
