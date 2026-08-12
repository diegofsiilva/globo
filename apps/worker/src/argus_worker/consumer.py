"""Loop de consumo: SQS -> validacao -> DynamoDB.

Garantias:

  - At-least-once na entrega (SQS) + escrita idempotente (chave derivada do
    conteudo) = efeito de exactly-once no DynamoDB.
  - Mensagem so e apagada da fila depois que TODOS os eventos dela foram
    gravados ou desviados para a DLQ. Falha de escrita segura o delete, o SQS
    devolve a mensagem e o redrive tenta de novo.
  - Payload que nunca vai funcionar (JSON quebrado, envelope invalido, item
    acima de 400 KB) vai direto para a DLQ com o motivo anexado, em vez de
    queimar as 5 tentativas do redrive para chegar no mesmo lugar.
"""

from __future__ import annotations

import json
import logging
import signal
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
from pydantic import ValidationError

from .config import Config
from .keys import build_item
from .models import parse_event
from .observability import Metrics
from .repository import EventRepository, ItemTooLarge, check_size

log = logging.getLogger(__name__)


class Consumer:
    def __init__(
        self,
        *,
        config: Config,
        sqs_client,
        repository: EventRepository,
        metrics: Metrics,
    ) -> None:
        self._config = config
        self._sqs = sqs_client
        self._repo = repository
        self._metrics = metrics
        self._running = True

    # ----------------------------------------------------------------- #
    # Ciclo de vida
    # ----------------------------------------------------------------- #

    def install_signal_handlers(self) -> None:
        """SIGTERM do ECS encerra apos o ciclo atual, sem largar mensagem em voo."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._request_stop)

    def _request_stop(self, signum, _frame) -> None:
        log.info(
            "sinal recebido, encerrando apos o ciclo atual", extra={"signal": signum}
        )
        self._running = False

    def run(self) -> None:
        log.info(
            "worker iniciado",
            extra={
                "queue_url": self._config.queue_url,
                "table_name": self._config.table_name,
                "batch_size": self._config.batch_size,
            },
        )
        while self._running:
            try:
                self.run_once()
            except ClientError:
                # Falha de API (throttle, rede). Nao apagamos nada, entao as
                # mensagens voltam a ficar visiveis sozinhas.
                log.error("erro de AWS no ciclo, seguindo", exc_info=True)
                self._metrics.count("CycleErrors")
                time.sleep(1.0)
            except Exception:
                log.exception("erro inesperado no ciclo, seguindo")
                self._metrics.count("CycleErrors")
                time.sleep(1.0)
            finally:
                self._metrics.flush()
        log.info("worker encerrado")

    # ----------------------------------------------------------------- #
    # Um ciclo
    # ----------------------------------------------------------------- #

    def run_once(self) -> int:
        """Processa um lote. Devolve quantos eventos foram gravados."""
        wait_started = time.monotonic()
        messages = self._receive()
        # O cronometro de CycleLatency comeca AQUI, depois do receive. O long
        # polling bloqueia ate 20s esperando mensagem, e incluir essa espera
        # ociosa faria a metrica reportar "13s de latencia" quando o
        # processamento real levou 400ms -- numero que assusta a toa no painel.
        started = time.monotonic()
        self._metrics.duration_ms("PollWait", (started - wait_started) * 1000)
        self._touch_heartbeat()

        if not messages:
            return 0

        self._metrics.count("MessagesReceived", len(messages))

        items: list[dict[str, Any]] = []
        keys_by_message: dict[str, set[str]] = {}
        handled: list[dict[str, Any]] = []

        for message in messages:
            message_id = message["MessageId"]
            message_items, quarantined, fatal = self._process_message(message)

            if fatal:
                # Nao conseguimos nem desviar para a DLQ: deixa a mensagem
                # voltar para a fila em vez de perder o evento.
                continue

            keys_by_message[message_id] = {
                f"{item['pk']}|{item['sk']}" for item in message_items
            }
            items.extend(message_items)

            if not message_items:
                # Tudo que tinha nessa mensagem foi para a DLQ: ja resolvida.
                handled.append(message)

            if quarantined:
                self._metrics.count("EventsQuarantined", quarantined)

        failed_keys = self._repo.put_many(items) if items else set()

        # Contamos por chave unica, nao por evento recebido: eventos identicos
        # colapsam numa linha so, e inflar EventsWritten com a duplicata daria
        # um numero de ingestao que nao bate com o que esta no DynamoDB.
        unique_keys = {f"{item['pk']}|{item['sk']}" for item in items}
        duplicates = len(items) - len(unique_keys)

        written = len(unique_keys - failed_keys)
        if written:
            self._metrics.count("EventsWritten", written)
        if failed_keys:
            self._metrics.count("EventsWriteFailed", len(failed_keys))
        if duplicates:
            # Taxa de reentrega do SQS: util para saber se o visibility timeout
            # esta curto demais para o tempo de processamento.
            self._metrics.count("EventsDeduplicated", duplicates)

        for message in messages:
            message_id = message["MessageId"]
            keys = keys_by_message.get(message_id)
            if keys is None or not keys:
                continue  # ja tratada acima, ou fatal
            if keys & failed_keys:
                log.warning(
                    "mensagem mantida na fila para redrive",
                    extra={"message_id": message_id, "failed": len(keys & failed_keys)},
                )
                continue
            handled.append(message)

        self._delete(handled)
        self._metrics.duration_ms("CycleLatency", (time.monotonic() - started) * 1000)
        return written

    # ----------------------------------------------------------------- #
    # Etapas
    # ----------------------------------------------------------------- #

    def _receive(self) -> list[dict[str, Any]]:
        response = self._sqs.receive_message(
            QueueUrl=self._config.queue_url,
            MaxNumberOfMessages=self._config.batch_size,
            WaitTimeSeconds=self._config.wait_time_seconds,
            VisibilityTimeout=self._config.visibility_timeout_seconds,
            MessageAttributeNames=["All"],
            AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
        )
        return response.get("Messages", [])

    def _process_message(
        self, message: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], int, bool]:
        """Devolve (itens prontos, quantos foram para a DLQ, houve falha fatal)."""
        message_id = message["MessageId"]

        try:
            raw_events = _extract_events(message.get("Body", ""))
        except ValueError as exc:
            ok = self._quarantine(message.get("Body", ""), str(exc), message_id)
            return [], 1 if ok else 0, not ok

        self._metrics.count("EventsReceived", len(raw_events))

        ingested_at = datetime.now(UTC)
        items: list[dict[str, Any]] = []
        quarantined = 0

        for raw in raw_events:
            try:
                event, is_known = parse_event(raw)
            except (ValidationError, TypeError) as exc:
                if self._quarantine(raw, f"validacao: {exc}", message_id):
                    quarantined += 1
                    continue
                return [], quarantined, True

            if not is_known:
                self._metrics.count("EventsUnknownType")
                log.info(
                    "tipo de evento desconhecido, gravado como generico",
                    extra={"event_name": event.event_name, "message_id": message_id},
                )

            if self._missing_recommended(event):
                self._metrics.count("EventsIncomplete")

            item = build_item(
                event,
                ingested_at=ingested_at,
                retention_days=self._config.retention_days,
                gsi1_shards=self._config.gsi1_shards,
                max_clock_skew_days=self._config.max_clock_skew_days,
            )

            try:
                check_size(item)
            except ItemTooLarge as exc:
                if self._quarantine(raw, str(exc), message_id):
                    quarantined += 1
                    continue
                return [], quarantined, True

            items.append(item)

        return items, quarantined, False

    def _missing_recommended(self, event) -> bool:
        return any(
            getattr(event, name, None) is None for name in self._config.recommended_fields
        )

    def _quarantine(self, payload: Any, reason: str, message_id: str) -> bool:
        """Manda o payload para a DLQ com o motivo. False se nem isso funcionou."""
        body = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False, default=str)
        )
        try:
            self._sqs.send_message(
                QueueUrl=self._config.dlq_url,
                MessageBody=body,
                MessageAttributes={
                    "FailureReason": {
                        "DataType": "String",
                        "StringValue": reason[:250],
                    },
                    "SourceMessageId": {
                        "DataType": "String",
                        "StringValue": message_id,
                    },
                },
            )
        except ClientError:
            log.error(
                "falha ao enviar para a DLQ, mensagem volta para a fila",
                extra={"message_id": message_id, "reason": reason},
                exc_info=True,
            )
            return False

        log.warning(
            "evento desviado para a DLQ",
            extra={"message_id": message_id, "reason": reason},
        )
        return True

    def _delete(self, messages: list[dict[str, Any]]) -> None:
        if not messages:
            return
        # DeleteMessageBatch aceita 10 por chamada -- o mesmo teto do receive,
        # entao na pratica e sempre uma chamada so.
        for start in range(0, len(messages), 10):
            chunk = messages[start : start + 10]
            response = self._sqs.delete_message_batch(
                QueueUrl=self._config.queue_url,
                Entries=[
                    {"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]}
                    for i, m in enumerate(chunk)
                ],
            )
            failed = response.get("Failed", [])
            if failed:
                # Nao e perda de dado: sem delete, o SQS reentrega e a escrita
                # idempotente absorve a repeticao.
                log.warning(
                    "falha ao apagar mensagens da fila",
                    extra={"failed": len(failed)},
                )
                self._metrics.count("DeleteFailed", len(failed))
            self._metrics.count("MessagesDeleted", len(chunk) - len(failed))

    def _touch_heartbeat(self) -> None:
        """Marca vida para o HEALTHCHECK do container."""
        try:
            Path(self._config.heartbeat_path).write_text(
                str(int(time.time())), encoding="utf-8"
            )
        except OSError:
            log.warning("nao consegui escrever o heartbeat", exc_info=True)


# --------------------------------------------------------------------------- #
# Parsing do corpo da mensagem
# --------------------------------------------------------------------------- #


def _extract_events(body: str) -> list[dict[str, Any]]:
    """Aceita as tres formas que a API pode entregar.

    O API Gateway repassa o corpo do POST cru para o SQS, entao o formato e o
    que o cliente mandou: um evento, uma lista de eventos, ou um envelope
    {"events": [...]}.
    """
    if not body or not body.strip():
        raise ValueError("corpo da mensagem vazio")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalido: {exc}") from exc

    if isinstance(parsed, list):
        events = parsed
    elif isinstance(parsed, dict):
        events = parsed["events"] if isinstance(parsed.get("events"), list) else [parsed]
    else:
        raise ValueError(f"esperava objeto ou lista, recebi {type(parsed).__name__}")

    if not events:
        raise ValueError("nenhum evento no corpo da mensagem")
    return events
