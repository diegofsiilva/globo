"""Executa consultas do agente sobre um caso sintético, sem banco ou modelo."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

MAX_ITEMS = 200
MAX_CALLS = 12


def _instant(value: str) -> dt.datetime:
    """Converte um instante UTC do contrato ou rejeita horário sem fuso."""
    instant = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("instante precisa conter fuso horário")
    return instant.astimezone(dt.UTC)


def _canonical(value: Any) -> str:
    """Serializa uma estrutura com ordem estável para digest e cursor."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    """Calcula SHA-256 da representação canônica."""
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _fact_id(fact: dict[str, Any]) -> str:
    """Identifica uma versão de fato sem colisão com outra versão."""
    return f"{fact['fact_key']}:{fact['version_lsn']}"


class CaseReader:
    """Mantém uma fotografia sintética imutável e oferece três consultas."""

    def __init__(self, case: dict[str, Any]) -> None:
        """Seleciona a última versão visível de cada fato no checkpoint."""
        if case.get("origin") not in {"synthetic", "database"}:
            raise ValueError("origem do recorte inválida")
        self.origin = case["origin"]
        self.case_id = case["case_id"]
        self.sim_now = _instant(case["sim_now"])
        self.input_lsn = int(case["input_lsn"])
        visible: dict[str, dict[str, Any]] = {}
        for fact in case["facts"]:
            if not isinstance(fact["fact_key"], str) or len(fact["fact_key"]) != 64:
                raise ValueError("fact_key inválida")
            if (
                fact["version_lsn"] > self.input_lsn
                or _instant(fact["available_at"]) > self.sim_now
                or _instant(fact["event_start"]) > self.sim_now
            ):
                continue
            previous = visible.get(fact["fact_key"])
            if previous is None or fact["version_lsn"] > previous["version_lsn"]:
                visible[fact["fact_key"]] = fact
        self.facts = tuple(
            sorted(
                (fact for fact in visible.values() if not fact["is_deleted"]),
                key=lambda fact: (fact["fact_key"], fact["version_lsn"]),
            )
        )
        self.digest = _digest([(_fact_id(fact), fact["role"]) for fact in self.facts])
        scope = _digest([self.case_id, self.digest])[:16]
        self.recorte_id = f"{self.origin}:{case['checkpoint_id']}:{scope}"

    def _window(self, inicio: str, fim: str) -> tuple[dt.datetime, dt.datetime]:
        """Recusa uma janela invertida ou posterior ao presente simulado."""
        start, end = _instant(inicio), _instant(fim)
        if start >= end or end > self.sim_now:
            raise ValueError("janela fora do recorte")
        return start, end

    def _page(
        self, tool: str, params: dict[str, Any], items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Pagina com cursor vinculado ao recorte, à ferramenta e aos filtros."""
        cursor = params.get("cursor")
        filters = {key: value for key, value in params.items() if key != "cursor"}
        signature = _digest([self.recorte_id, tool, filters])
        offset = 0
        if cursor is not None:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
                if decoded["signature"] != signature:
                    raise ValueError("cursor de outro filtro")
                offset = decoded["offset"]
                if not isinstance(offset, int) or offset < 0 or offset >= len(items):
                    raise ValueError("cursor inválido")
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError("cursor inválido") from error
        limit = filters.get("limit", MAX_ITEMS)
        if not isinstance(limit, int) or not 1 <= limit <= MAX_ITEMS:
            raise ValueError("limit deve estar entre 1 e 200")
        page = items[offset : offset + limit]
        next_offset = offset + len(page)
        has_more = next_offset < len(items)
        next_cursor = None
        if has_more:
            token = {"signature": signature, "offset": next_offset}
            next_cursor = base64.urlsafe_b64encode(_canonical(token).encode()).decode()
        limitations = []
        if not page:
            limitations.append("sem_fatos_no_recorte_consultado")
        if has_more:
            limitations.append("pagina_limitada")
        return {
            "recorte_id": self.recorte_id,
            "tool": tool,
            "items": page,
            "returned": len(page),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "limitations": limitations,
        }

    def inventariar_fatos(self, **params: Any) -> dict[str, Any]:
        """Agrupa fontes e métricas sem calcular anomalia ou ranking."""
        if set(params) - {"cursor", "limit"}:
            raise ValueError("filtro não aceito no inventário")
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for fact in self.facts:
            key = (
                fact["source"],
                fact["kind"],
                fact["entity"],
                fact["metric"],
                fact["dimension_type"] or "",
            )
            grouped[key].append(fact)
        items = []
        for key, facts in sorted(grouped.items()):
            items.append(
                {
                    "source": key[0],
                    "kind": key[1],
                    "entity": key[2],
                    "metric": key[3],
                    "dimension_type": key[4] or None,
                    "count": len(facts),
                    "event_start_min": min(f["event_start"] for f in facts),
                    "event_start_max": max(f["event_start"] for f in facts),
                    "available_at_min": min(f["available_at"] for f in facts),
                    "available_at_max": max(f["available_at"] for f in facts),
                    "has_null_value": any(f["value"] is None for f in facts),
                    "has_null_sample_size": any(f["sample_size"] is None for f in facts),
                    "group_ref": _digest([_fact_id(f) for f in facts]),
                }
            )
        result = self._page("inventariar_fatos", params, items)
        result["sim_now"] = self.sim_now.isoformat()
        return result

    def consultar_serie(self, **params: Any) -> dict[str, Any]:
        """Retorna métricas de uma série inventariada em uma janela explícita."""
        required = {"source", "entity", "metric", "inicio", "fim"}
        allowed = required | {"dimension_type", "dimension_value", "limit", "cursor"}
        if not required <= set(params) or set(params) - allowed:
            raise ValueError("parâmetros inválidos para consultar_serie")
        start, end = self._window(params["inicio"], params["fim"])
        dimension = (params.get("dimension_type"), params.get("dimension_value"))
        if (dimension[0] is None) != (dimension[1] is None):
            raise ValueError("dimensão exige tipo e valor")
        if dimension[1] in {"?", "(desconhecido)"}:
            raise ValueError("dimensão desconhecida")
        series = [
            fact
            for fact in self.facts
            if fact["kind"] == "metric"
            and all(
                fact[field] == params[field] for field in ("source", "entity", "metric")
            )
        ]
        if not series:
            raise ValueError("série não consta do inventário")
        if dimension != (None, None) and not any(
            (fact["dimension_type"], fact["dimension_value"]) == dimension
            for fact in series
        ):
            raise ValueError("dimensão não consta do recorte")
        items = [
            self._project(fact)
            for fact in sorted(
                series,
                key=lambda fact: (
                    fact["event_start"],
                    fact["fact_key"],
                    fact["version_lsn"],
                ),
            )
            if start <= _instant(fact["event_start"]) <= end
            and (fact["dimension_type"], fact["dimension_value"]) == dimension
        ]
        return self._page("consultar_serie", params, items)

    def consultar_contexto(self, **params: Any) -> dict[str, Any]:
        """Retorna fatos de uma fonte ou entidade, incluindo eventos sobrepostos."""
        required = {"inicio", "fim"}
        allowed = required | {"source", "entity", "kinds", "limit", "cursor"}
        if not required <= set(params) or set(params) - allowed:
            raise ValueError("parâmetros inválidos para consultar_contexto")
        source, entity = params.get("source"), params.get("entity")
        if not source and not entity:
            raise ValueError("fonte ou entidade obrigatória")
        start, end = self._window(params["inicio"], params["fim"])
        kinds = params.get("kinds", ["metric", "context"])
        if not isinstance(kinds, list) or not kinds or set(kinds) - {"metric", "context"}:
            raise ValueError("kinds inválidos")
        if source and not any(fact["source"] == source for fact in self.facts):
            raise ValueError("fonte não consta do inventário")
        if entity and not any(fact["entity"] == entity for fact in self.facts):
            raise ValueError("entidade não consta do inventário")
        items = []
        for fact in sorted(
            self.facts,
            key=lambda fact: (
                fact["event_start"],
                fact["source"],
                fact["fact_key"],
                fact["version_lsn"],
            ),
        ):
            began = _instant(fact["event_start"])
            finished = _instant(fact["event_end"]) if fact["event_end"] else began
            if (
                (not source or fact["source"] == source)
                and (not entity or fact["entity"] == entity)
                and fact["kind"] in kinds
                and began <= end
                and finished >= start
            ):
                items.append(self._project(fact))
        return self._page("consultar_contexto", params, items)

    @staticmethod
    def _project(fact: dict[str, Any]) -> dict[str, Any]:
        """Expõe somente campos permitidos, sem payload bruto ou identificadores."""
        fields = (
            "kind",
            "source",
            "entity",
            "metric",
            "event_start",
            "event_end",
            "available_at",
            "value",
            "sample_size",
            "dimension_type",
            "dimension_value",
        )
        return {"fact_id": _fact_id(fact), **{field: fact[field] for field in fields}}


def execute_queries(
    reader: CaseReader, queries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Executa uma sequência limitada de consultas sobre o mesmo recorte."""
    if len(queries) > MAX_CALLS:
        raise ValueError("caso excede o teto de 12 chamadas")
    methods = {
        "inventariar_fatos": reader.inventariar_fatos,
        "consultar_serie": reader.consultar_serie,
        "consultar_contexto": reader.consultar_contexto,
    }
    responses = []
    for query in queries:
        method = methods.get(query["tool"])
        if method is None:
            raise ValueError("ferramenta não permitida")
        responses.append(method(**query["params"]))
    return responses


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Executa as consultas declaradas pelo caso e registra as respostas."""
    reader = CaseReader(case)
    responses = execute_queries(reader, case["queries"])
    return {
        "case_id": reader.case_id,
        "origin": reader.origin,
        "checkpoint_id": case["checkpoint_id"],
        "sim_now": case["sim_now"],
        "input_lsn": reader.input_lsn,
        "recorte_id": reader.recorte_id,
        "pilot_digest": reader.digest,
        "responses": responses,
    }


def main() -> None:
    """Imprime um registro JSON reproduzível a partir de um caso sintético."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8"))
    print(json.dumps(run_case(case), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
