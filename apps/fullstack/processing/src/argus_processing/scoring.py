"""Score, cobertura e confianca explicaveis."""

from __future__ import annotations

from collections.abc import Mapping

from argus_processing.domain import Feature

WEIGHTS = {"A": 0.25, "T": 0.20, "C": 0.20, "E": 0.15, "I": 0.15, "Q": 0.05}


def score_features(
    values: Mapping[str, tuple[str, float | None, str]],
    *,
    contradiction: float,
) -> tuple[float, float, str, tuple[Feature, ...]]:
    """Calcula score, cobertura e confiança a partir das features disponíveis.

    Cada feature aplicável contribui com seu peso proporcional ao valor
    normalizado entre zero e um. Features indisponíveis não viram zero: elas
    reduzem a cobertura, enquanto features não aplicáveis saem do denominador.
    A contradição reduz o score e também limita a confiança.

    Args:
        values: Mapa de identificador da feature para aplicabilidade, valor
            opcional e explicação que será preservada no resultado.
        contradiction: Força agregada das evidências contrárias, no intervalo
            esperado de zero a um.

    Returns:
        Tupla com score de zero a cem, cobertura de zero a um, nível de
        confiança e detalhamento das features com suas contribuições.
    """
    available_weight = 0.0
    applicable_weight = 0.0
    weighted = 0.0
    features: list[Feature] = []
    for name, weight in WEIGHTS.items():
        applicability, value, explanation = values.get(
            name, ("unavailable", None, "feature aplicavel indisponivel")
        )
        if applicability != "not_applicable":
            applicable_weight += weight
        contribution = None
        if applicability == "available" and value is not None:
            normalized = max(0.0, min(1.0, value))
            available_weight += weight
            weighted += weight * normalized
            contribution = weight * normalized
            value = normalized
        features.append(
            Feature(name, applicability, value, weight, contribution, explanation)
        )

    base = 100.0 * weighted / available_weight if available_weight else 0.0
    score = max(0.0, min(100.0, base - 30.0 * contradiction))
    coverage = available_weight / applicable_weight if applicable_weight else 1.0
    q_value = values.get("Q", ("unavailable", None, ""))[1]
    if (
        score >= 80
        and coverage >= 0.80
        and (q_value or 0.0) >= 0.70
        and contradiction < 0.5
    ):
        confidence = "high"
    elif score >= 60 and coverage >= 0.60 and contradiction < 0.8:
        confidence = "medium"
    else:
        confidence = "low"
    features.append(
        Feature(
            "X",
            "available",
            contradiction,
            0.0,
            -30.0 * contradiction,
            "forca maxima das evidencias contrarias",
        )
    )
    return score, coverage, confidence, tuple(features)
