"""Identidade do evento e montagem da linha de `bronze.event`.

Na v2 este modulo montava as chaves do modelo single-table do DynamoDB
(SESSION#, EVT#, DEV# e o shard da GSI1). Nada disso sobrevive: o PostgreSQL
resolve os tres padroes de acesso com indice, e o sharding da GSI1 existia
apenas para contornar o teto de 1000 WCU por particao do DynamoDB -- um limite
que nao existe aqui.

O que sobrevive, e e o que importa, e `build_event_id`: o id deterministico
derivado do conteudo. E ele que faz a reentrega at-least-once do SQS virar um
`ON CONFLICT DO NOTHING` em vez de uma linha duplicada.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import BaseEvent

# Quantos caracteres do hash formam o id. 32 hex = 128 bits: com milhoes de
# eventos por segundo a chance de colisao segue desprezivel, e eventos identicos
# DEVEM colidir -- e assim que a idempotencia funciona.
EVENT_ID_CHARS = 32


def canonical_json(payload: dict[str, Any]) -> str:
    """Serializacao estavel: mesma entrada gera sempre os mesmos bytes.

    `sort_keys` e o que torna o hash reproduzivel. Sem ele, o mesmo evento
    reenviado com as chaves em outra ordem (o que acontece de verdade, porque
    JSON nao promete ordem) geraria um id diferente e viraria uma duplicata.

    Args:
        payload (dict[str, Any]): Dicionario com os dados do evento.

    Returns:
        str: String JSON canonica com chaves ordenadas.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def build_event_id(event: BaseEvent) -> str:
    """Id deterministico do evento.

    Se o cliente mandou `event_id`, ele manda -- respeitamos a identidade que a
    origem escolheu. Senao, derivamos do conteudo: duas entregas do mesmo evento
    produzem a mesma chave, entao a reentrega do SQS (at-least-once por design)
    colide de proposito e o `ON CONFLICT DO NOTHING` a absorve.

    Idempotencia sem leitura previa e sem transacao serializavel.

    Args:
        event (BaseEvent): Evento ja validado.

    Returns:
        str: Identificador de 32 caracteres hexadecimais.
    """
    if event.event_id:
        return event.event_id
    bruto = canonical_json(event.model_dump(mode="json", exclude_none=True))
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:EVENT_ID_CHARS]


def clock_skew(moment: datetime, max_days: int) -> bool:
    """Diz se o timestamp do evento esta absurdamente longe de agora.

    Relogio de TV e notoriamente errado -- aparelho sem NTP, fuso configurado na
    mao, relogio zerado depois de queda de energia. O evento com desvio e
    MARCADO, nunca descartado: jogar fora perderia justamente o aparelho com
    problema, que costuma ser o que a investigacao procura.

    Args:
        moment (datetime): Timestamp declarado pelo evento.
        max_days (int): Desvio tolerado, em dias.

    Returns:
        bool: True se o desvio ultrapassa o limite.
    """
    return abs(datetime.now(UTC) - moment) > timedelta(days=max_days)


# Campos que viram COLUNA em bronze.event. O resto do evento vai para `payload`.
CAMPOS_ENVELOPE = frozenset(
    {
        "event_id",
        "timestamp",
        "event_name",
        "session_id",
        "device_id",
        "user_id",
        "app_bucket",
        "app_env",
        "app_target",
        "app_version",
        "device_manufacturer",
        "device_model",
        "device_model_year",
        "device_os",
        "device_os_version",
        "route_path",
        "route_params",
        "duration",
    }
)


def build_row(
    event: BaseEvent,
    *,
    ingested_at: datetime,
    max_clock_skew_days: int = 365,
) -> dict[str, Any]:
    """Monta a linha de `bronze.event` a partir do evento validado.

    A divisao entre coluna e `payload` segue o schema de 005_bronze_event.sql: o
    envelope comum e tipado (as telas Explorar e Recorte filtram por ele, e
    filtro precisa de indice), e o que e especifico do tipo -- request_*,
    media_*, error_*, capabilities_* -- fica em jsonb.

    Args:
        event (BaseEvent): Evento ja validado pelo Pydantic.
        ingested_at (datetime): Instante em que o lote entrou no worker.
        max_clock_skew_days (int): Desvio de relogio tolerado antes de marcar.

    Returns:
        dict[str, Any]: Linha pronta para EventRepository.put_many.
    """
    bruto = event.model_dump(mode="python")
    payload = {
        k: v for k, v in bruto.items() if k not in CAMPOS_ENVELOPE and v is not None
    }

    if clock_skew(event.timestamp, max_clock_skew_days):
        # Vai no payload, e nao numa coluna: e sinal de qualidade do dado, nao
        # dimensao de consulta. Ninguem filtra a tela por "eventos com relogio
        # errado" -- mas quem investiga um numero estranho precisa achar isso.
        payload["clock_skew"] = True

    # route_params chega como dict ou como string, conforme a versao do app.
    # Normalizar aqui, e nao no banco, e o que mantem a coluna jsonb utilizavel.
    route_params = bruto.get("route_params")
    if isinstance(route_params, str):
        try:
            route_params = json.loads(route_params)
        except (json.JSONDecodeError, TypeError):
            route_params = {"raw": route_params}

    # device_model_year vem como int, como string ("2019") ou como texto livre
    # ("unknown"), dependendo do firmware -- e "unknown" e valor REAL do parque,
    # nao lixo.
    #
    # A coluna e integer, entao o que nao converte nao cabe la. Mas descartar
    # tambem esta fora de questao: e a mesma regra do `_extra` da bronze, de
    # nunca perder o que a origem mandou. O valor original vai para o payload, e
    # a coluna fica nula -- quem filtra por ano usa a coluna, quem investiga um
    # aparelho especifico ainda encontra o "unknown".
    ano = bruto.get("device_model_year")
    if isinstance(ano, str):
        if ano.strip().isdigit():
            ano = int(ano)
        else:
            payload["device_model_year"] = ano
            ano = None

    return {
        "event_id": build_event_id(event),
        "ts": event.timestamp,
        "event_name": event.event_name,
        "session_id": event.session_id,
        "device_id": event.device_id,
        "user_id": event.user_id,
        "app_bucket": event.app_bucket,
        "app_env": event.app_env,
        "app_target": event.app_target,
        "app_version": event.app_version,
        "device_manufacturer": event.device_manufacturer,
        "device_model": event.device_model,
        "device_model_year": ano,
        "device_os": event.device_os,
        "device_os_version": event.device_os_version,
        "route_path": event.route_path,
        "route_params": route_params,
        "duration": event.duration,
        "payload": payload,
        "_captured_at": ingested_at,
    }
