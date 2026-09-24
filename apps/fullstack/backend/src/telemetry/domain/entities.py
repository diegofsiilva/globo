"""Entidades de domínio da aplicação de telemetria."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """Um evento de telemetria, como ele existe no DynamoDB.

    A fonte de verdade e o que o worker de ingestao grava (ver worker/), nao o
    que seria conveniente para a API. Tres consequencias disso:

    - `event_id` e uma string, nao UUID. O worker deriva a identidade do hash
      sha256 do conteudo do evento, e e isso que da idempotencia: reentrega do
      SQS grava por cima em vez de duplicar. Sao 64 caracteres hex, que nao
      cabem num UUID.

    - `device_model_year` aceita texto. Boa parte do parque responde "unknown"
      em vez de um ano, e recusar esses eventos descartaria dois dos seis tipos.

    - `duration_ms` e derivado: o DynamoDB guarda `duration` em SEGUNDOS, como
      o app envia. A conversao acontece na leitura porque milissegundo e a
      unidade que o dashboard usa.

    Campos especificos de cada tipo (error_*, media_*, capabilities_*,
    request_*) ficam em `attributes`. Sao seis tipos de evento com colunas
    diferentes, e promover todos a atributo de primeira classe deixaria a
    entidade com dezenas de campos nulos.
    """

    event_id: str
    event_name: str
    occurred_at: datetime
    session_id: str
    device_id: str

    # Quando o worker gravou. Difere de occurred_at em replay de dado
    # historico, e a diferenca entre os dois e o lag da ingestao.
    ingested_at: datetime | None = None

    duration_ms: float | None = None
    action: str | None = None
    route_path: str | None = None

    app_bucket: str | None = None
    app_env: str | None = None
    app_target: str | None = None
    app_version: str | None = None
    app_resolution: str | None = None

    device_manufacturer: str | None = None
    device_model: str | None = None
    device_model_year: int | str | None = None
    device_os: str | None = None
    device_os_version: str | None = None
    device_resolution: str | None = None

    # Nunca o user_id cru. O DynamoDB guarda o identificador original porque a
    # ingestao nao o transforma, entao o hash acontece aqui, na saida.
    user_id_hash: str | None = None

    # Relogio do aparelho muito fora do esperado. O worker sinaliza em vez de
    # descartar, e o dashboard precisa poder filtrar.
    clock_skew: bool = False

    attributes: dict[str, Any] = field(default_factory=dict)
