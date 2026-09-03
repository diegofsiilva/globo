"""Schema do change event que chega em POST /v1/changes.

Um change event descreve UMA mudanca em UMA linha de UMA tabela de origem
conhecida do Argus:

    {
      "source_table": "signal_bucket",
      "op": "u",
      "pk":     {"bts": 1784904300000, "source": "prometheus", ...},
      "before": {"...": "...", "value": 368.0},
      "after":  {"...": "...", "value": 412.0},
      "captured_at": "2026-07-24T12:20:00Z"
    }

O envelope e validado com rigor -- `source_table` errado escreveria em tabela
que nao existe, `op` errado aplicaria a operacao errada -- mas `pk`, `before` e
`after` sao jsonb livre de proposito. E o mesmo motivo da decisao 4 do plano: a
Globo pode acrescentar coluna a qualquer momento, e um schema estrito aqui
transformaria isso em perda de dado na borda, antes mesmo de o `_extra` ter
chance de absorver.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

# As tabelas de origem conhecidas. A lista fechada separa dois casos:
# tabela nova exige migration e vai para a DLQ; coluna nova cai em `_extra`.
# Confundir os dois faria o worker criar tabela sozinho, que e exatamente o
# que nao se quer.
TABELAS_CONHECIDAS = frozenset(
    {
        "app_error",
        "app_error_model",
        "app_error_version",
        "apollo_run",
        "ca_point",
        "ca_run",
        "cdn_vod_shadow",
        "cdn_entity_tier",
        "collector_run",
        "dashboard_artifact",
        "device_hourly",
        "error_cat_hourly",
        "field_metrics",
        "geo_hourly",
        "incident_label",
        "incidents",
        "incidents_platform",
        "investigation_feedback",
        "isp_pop_daily",
        "live_active_15min",
        "live_error_attr_hourly",
        "live_event",
        "live_event_sde",
        "live_qoe_hourly",
        "nr_run",
        "operation_metrics",
        "player_hourly",
        "player_live_hourly",
        "prom_point",
        "prom_query",
        "prom_run",
        "prom_series",
        "rpaas_bucket",
        "rpaas_run",
        "service_overview",
        "signal_bucket",
        "signal_meta",
        "signal_point",
        "tsuru_event",
    }
)


class ChangeEvent(BaseModel):
    """Uma mudanca em uma linha de uma tabela da origem."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_table: str
    op: Literal["i", "u", "d", "r"]
    pk: dict[str, Any]
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    captured_at: dt.datetime
    run_id: int | None = None

    @field_validator("source_table")
    @classmethod
    def _tabela_conhecida(cls, value: str) -> str:
        """Recusa tabela fora das 33 do dump.

        Falhar aqui e melhor que falhar no INSERT: a mensagem vai para a DLQ com
        o nome da tabela no motivo, e quem investigar le "tabela desconhecida"
        em vez de um erro de relacao inexistente vindo do PostgreSQL.
        """
        if value not in TABELAS_CONHECIDAS:
            raise ValueError(
                f"tabela desconhecida: {value!r}. Tabela nova exige migration; "
                "coluna nova nao (cai em _extra)"
            )
        return value

    @field_validator("captured_at", mode="after")
    @classmethod
    def _para_utc(cls, value: dt.datetime) -> dt.datetime:
        """Timestamp sem fuso e tratado como UTC em vez de rejeitado."""
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value.astimezone(dt.UTC)

    @field_validator("pk")
    @classmethod
    def _pk_nao_vazia(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Sem chave primaria nao ha como aplicar o MERGE de forma idempotente."""
        if not value:
            raise ValueError("pk vazia: o MERGE nao tem como identificar a linha")
        return value


def parse_change(raw: dict[str, Any]) -> dict[str, Any]:
    """Valida um change event e devolve o dicionario pronto para o repositorio.

    Args:
        raw (dict[str, Any]): Change event cru, vindo da fila.

    Returns:
        dict[str, Any]: Change event validado.

    Raises:
        pydantic.ValidationError: Se o envelope estiver invalido.
        ValueError: Se a operacao for incoerente com o corpo.
    """
    evento = ChangeEvent.model_validate(raw)

    # Coerencia entre `op` e corpo. O banco nao tem como pegar isso: um update
    # sem `after` viraria simplesmente uma linha que o MERGE ignora em silencio,
    # e a mudanca sumiria sem nenhum sinal.
    if evento.op in ("i", "u", "r") and not evento.after:
        raise ValueError(f"op={evento.op!r} exige `after`, que veio vazio")

    return evento.model_dump(mode="python")
