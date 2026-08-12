"""Identidade do evento e chaves do DynamoDB.

Modelo single-table. Tres padroes de acesso, um por indice:

  tabela  pk=SESSION#<session_id>            sk=<ts>#<event_id>
          -> linha do tempo de uma sessao, em ordem cronologica

  GSI1    gsi1pk=EVT#<event_name>#<data>#<shard>   gsi1sk=<ts>#<event_id>
          -> todos os eventos de um tipo num dia ("erros de 13/07")

  GSI2    gsi2pk=DEV#<device_id>             gsi2sk=<ts>#<event_id>
          -> historico de um aparelho

O sufixo `#<shard>` na GSI1 nao e enfeite: sem ele, todo evento `request` de um
dia cairia na mesma particao, e uma particao do DynamoDB satura em 1000 WCU. Com
telemetria de um parque de TVs isso e o gargalo obvio. O shard e derivado do
hash do evento (distribuicao uniforme, deterministica), e a leitura vira um
fan-out de GSI1_SHARDS queries em paralelo -- custo de leitura identico, so mais
uma chamada. Em dev da pra usar GSI1_SHARDS=1 e ler com uma query so.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import BaseEvent

# Quantos caracteres do hash entram na sort key. 12 hex = 48 bits: com milhoes de
# eventos por segundo no mesmo timestamp a chance de colisao segue desprezivel, e
# eventos identicos DEVEM colidir (e assim que a idempotencia funciona).
EVENT_ID_SK_CHARS = 12


def canonical_json(payload: dict[str, Any]) -> str:
    """Serializacao estavel: mesma entrada, sempre os mesmos bytes."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def build_event_id(event: BaseEvent) -> str:
    """Id deterministico do evento.

    Se o cliente mandou `event_id`, ele manda. Senao, derivamos do conteudo:
    duas entregas do mesmo evento produzem a mesma chave, entao a reentrega do
    SQS (que e at-least-once por design) vira um overwrite identico no DynamoDB
    em vez de uma linha duplicada. Idempotencia sem leitura previa nem
    ConditionExpression.
    """
    if event.event_id:
        return event.event_id

    payload = event.model_dump(mode="json", exclude_none=True)
    payload.pop("event_id", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _sk_timestamp(moment: datetime) -> str:
    """ISO-8601 UTC com milissegundos -- ordenavel lexicograficamente."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def shard_for(event_id: str, shards: int) -> int:
    if shards <= 1:
        return 0
    return int(event_id[:8], 16) % shards


def build_item(
    event: BaseEvent,
    *,
    ingested_at: datetime,
    retention_days: int,
    gsi1_shards: int,
    max_clock_skew_days: int,
) -> dict[str, Any]:
    """Monta o item completo do DynamoDB a partir do evento validado."""
    event_id = build_event_id(event)
    short_id = event_id[:EVENT_ID_SK_CHARS]
    ts = _sk_timestamp(event.timestamp)
    day = event.timestamp.astimezone(UTC).strftime("%Y-%m-%d")
    shard = shard_for(event_id, gsi1_shards)

    item: dict[str, Any] = event.model_dump(mode="json", exclude_none=True)

    item["event_id"] = event_id
    item["pk"] = f"SESSION#{event.session_id}"
    item["sk"] = f"{ts}#{short_id}"
    item["gsi1pk"] = f"EVT#{event.event_name}#{day}#{shard}"
    item["gsi1sk"] = f"{ts}#{short_id}"
    item["gsi2pk"] = f"DEV#{event.device_id}"
    item["gsi2sk"] = f"{ts}#{short_id}"
    item["event_date"] = day
    item["ingested_at"] = _sk_timestamp(ingested_at)

    # TTL contado da ingestao, nao do horario do evento: replay de dado historico
    # nao pode nascer expirado.
    item["expires_at"] = int((ingested_at + timedelta(days=retention_days)).timestamp())

    # Relogio de TV erra feio. Sinalizamos o desvio grosseiro (1970, 2099) para
    # que as analises possam filtrar, mas nunca descartamos o evento.
    skew = abs((ingested_at - event.timestamp).days)
    if max_clock_skew_days > 0 and skew > max_clock_skew_days:
        item["clock_skew"] = True
        item["clock_skew_days"] = skew

    return item
