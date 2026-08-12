"""Entrypoint do container.

Uso:
    python -m argus_worker
"""

from __future__ import annotations

import sys

import boto3
from botocore.config import Config as BotoConfig

from .config import Config
from .consumer import Consumer
from .observability import Metrics, configure_logging
from .repository import EventRepository


def build_boto_config(config: Config) -> BotoConfig:
    return BotoConfig(
        region_name=config.region,
        # O retry adaptativo do botocore ja respeita o throttle do servico; o
        # retry do repository cuida so dos UnprocessedItems, que nao sao erro.
        retries={"max_attempts": 5, "mode": "adaptive"},
        # Precisa ser maior que o long polling do SQS, senao todo receive vazio
        # estoura timeout.
        read_timeout=config.wait_time_seconds + 10,
        connect_timeout=5,
        max_pool_connections=25,
    )


def main() -> int:
    try:
        config = Config.from_env()
    except (RuntimeError, ValueError) as exc:
        print(f"erro de configuracao: {exc}", file=sys.stderr)
        return 1

    log = configure_logging(config.log_level, config.service_name)
    boto_config = build_boto_config(config)

    session = boto3.session.Session()
    sqs = session.client("sqs", config=boto_config)
    dynamodb = session.client("dynamodb", config=boto_config)

    consumer = Consumer(
        config=config,
        sqs_client=sqs,
        repository=EventRepository(
            dynamodb, config.table_name, max_retries=config.write_max_retries
        ),
        metrics=Metrics(config.metrics_namespace, config.service_name),
    )
    consumer.install_signal_handlers()

    try:
        consumer.run()
    except Exception:
        log.exception("worker abortou")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
