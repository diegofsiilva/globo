"""Canario deterministico de qualidade das fontes."""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from collections.abc import Iterable

from argus_processing.catalog import Catalog
from argus_processing.domain import Fact, SourceQuality


def _clamp(value: float) -> float:
    """Prende um indicador a faixa [0, 1].

    As quatro dimensoes de qualidade sao razoes, e uma fonte que entrega mais
    buckets do que o esperado produziria completude acima de 1 -- que somaria ao
    score como se fosse qualidade extra.

    Args:
        value (float): Razao calculada.

    Returns:
        float: O valor dentro de [0, 1].
    """
    return max(0.0, min(1.0, value))


def evaluate_quality(
    facts: Iterable[Fact],
    catalog: Catalog,
    *,
    window_start: dt.datetime,
    window_end: dt.datetime,
    simulator_end: dt.datetime | None = None,
) -> tuple[SourceQuality, ...]:
    """Avalia a qualidade de cada fonte na janela do ciclo.

    O canario existe porque uma fonte SILENCIOSA e indistinguivel de uma fonte
    saudavel sem incidente: as duas produzem zero anomalia. Sem esta medida, o
    motor concluiria "nada de errado" justamente quando parou de enxergar.

    Args:
        facts (Iterable[Fact]): Fatos do ciclo. So `kind == "metric"` nos papeis
            `subject` e `quality` entram na conta.
        catalog (Catalog): Cadencia esperada e regras por fonte.
        window_start (datetime): Inicio da janela avaliada.
        window_end (datetime): Fim da janela avaliada.
        simulator_end (datetime | None): Ate onde o simulador chegou. Sem isto,
            a janela avaliada iria alem do que o simulador ja emitiu, e TODA
            fonte apareceria incompleta -- um alarme de qualidade que so mede o
            quanto o relogio virtual esta a frente da reproducao.

    Returns:
        tuple[SourceQuality, ...]: Um veredito por fonte conhecida, inclusive
            as que nao entregaram nada -- que sao justamente as que importam.
    """
    by_source: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        if fact.kind == "metric" and fact.role in {"subject", "quality"}:
            by_source[fact.source].append(fact)

    result: list[SourceQuality] = []
    effective_end = min(window_end, simulator_end) if simulator_end else window_end
    for source in sorted(set(by_source) | set(catalog.raw["sources.json"]) - {"default"}):
        cadence = int(catalog.source(source)["cadence_seconds"])
        rows = by_source.get(source, [])
        subject_rows = [fact for fact in rows if fact.role == "subject"]
        expected = max(
            0, math.floor((effective_end - window_start).total_seconds() / cadence)
        )
        buckets = {f.event_start for f in subject_rows}
        observed = len(buckets)
        last = max((fact.event_start for fact in rows), default=None)
        last_available = max((fact.available_at for fact in rows), default=None)

        if last_available is None:
            freshness = 0.0
            status = "silent" if expected > 0 else "unknown"
        else:
            # Freshness usa o instante em que o dado se tornou utilizavel. Isso
            # absorve o atraso causal estrutural de 28 h da NPAW sem fingir que
            # o evento aconteceu agora.
            gap_cadences = max(
                0.0, (effective_end - last_available).total_seconds() / cadence
            )
            freshness = _clamp(1.0 - max(0.0, gap_cadences - 1.0) / 2.0)
            status = (
                "healthy"
                if gap_cadences <= 1.5
                else ("delayed" if gap_cadences <= 3.0 else "silent")
            )

        completeness = _clamp(observed / expected) if expected else 1.0
        assessed_rows = subject_rows or rows
        valid_rows = [
            f for f in assessed_rows if f.value is not None and math.isfinite(f.value)
        ]
        validity = len(valid_rows) / len(assessed_rows) if assessed_rows else 0.0
        consistent_rows = [
            f for f in valid_rows if f.sample_size is None or f.sample_size >= 0
        ]
        consistency = len(consistent_rows) / len(assessed_rows) if assessed_rows else 0.0
        score = (
            0.35 * freshness + 0.35 * completeness + 0.15 * validity + 0.15 * consistency
        )

        if assessed_rows and (validity < 0.99 or consistency < 0.99):
            status = "invalid"
        elif (
            expected > 0
            and rows
            and (completeness < 0.70 or (completeness < 0.95 and status == "healthy"))
        ):
            status = "incomplete"

        result.append(
            SourceQuality(
                source=source,
                expected_cadence_seconds=cadence,
                last_observation_at=last,
                freshness=freshness,
                completeness=completeness,
                validity=validity,
                consistency=consistency,
                quality_score=score,
                status=status,
                expected_buckets=expected,
                observed_buckets=observed,
                details={
                    "gap_cadences": (None if last_available is None else gap_cadences),
                    "last_available_at": (
                        last_available.isoformat() if last_available else None
                    ),
                    "evaluated_at": effective_end.isoformat(),
                },
            )
        )
    return tuple(result)
