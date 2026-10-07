"""Detector EWMA circadiano estritamente causal."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from zoneinfo import ZoneInfo

from argus_processing.catalog import Catalog, MetricPolicy
from argus_processing.domain import Anomaly, Baseline, Fact


def _transform(value: float, policy: MetricPolicy) -> float:
    """Leva a metrica para o espaco em que o baseline e calculado.

    Metrica de latencia tem cauda longa a direita: a media e o desvio-padrao no
    espaco original sao dominados por poucos picos, e o z-score resultante
    marcaria como anomalia qualquer dia um pouco mais lento. `log1p` comprime a
    cauda e faz a distribuicao ficar proxima da normal, que e a suposicao do
    z-score.

    Args:
        value (float): Valor observado, na unidade nativa.
        policy (MetricPolicy): Politica da metrica; decide se ha transformacao.

    Returns:
        float: O valor no espaco do baseline.
    """
    return math.log1p(max(value, 0.0)) if policy.transform == "log1p" else value


def _inverse(value: float, policy: MetricPolicy) -> float:
    """Traz um valor do espaco do baseline de volta a unidade nativa.

    Usado no que sai para o operador: `expected` precisa ser mostrado em
    milissegundos, e nao em log de milissegundos.

    Args:
        value (float): Valor no espaco do baseline.
        policy (MetricPolicy): Politica da metrica.

    Returns:
        float: O valor na unidade original.
    """
    return math.expm1(value) if policy.transform == "log1p" else value


def _material(observed: float, expected: float, policy: MetricPolicy) -> bool:
    """Decide se o desvio e grande o bastante para alguem se importar.

    Exige as DUAS condicoes, absoluta e relativa, de proposito. So relativa
    dispararia com 1 ms virando 3 ms numa serie muito estavel; so absoluta
    dispararia com 50 ms de variacao numa metrica que normalmente oscila 500 ms.
    Um z-score alto significa "estatisticamente incomum", que nao e o mesmo que
    "operacionalmente relevante".

    Args:
        observed (float): Valor observado.
        expected (float): Valor esperado pelo baseline.
        policy (MetricPolicy): Limiares de materialidade da metrica.

    Returns:
        bool: `True` quando o desvio passa nos dois limiares.
    """
    absolute = abs(observed - expected)
    relative = absolute / max(abs(expected), 1e-12)
    return (
        absolute >= policy.materiality_absolute
        and relative >= policy.materiality_relative
    )


def _bad_direction(observed: float, expected: float, policy: MetricPolicy) -> bool:
    """Decide se o desvio aponta para o lado RUIM da metrica.

    A direcao importa: taxa de erro caindo e boa noticia, latencia caindo
    tambem. Sem este filtro o motor abriria hipotese para explicar uma melhora,
    e o operador gastaria a atencao dele nisso.

    Args:
        observed (float): Valor observado.
        expected (float): Valor esperado pelo baseline.
        policy (MetricPolicy): Politica da metrica; `direction` e `up`, `down`
            ou qualquer outro valor para "os dois lados importam".

    Returns:
        bool: `True` quando o desvio e na direcao indesejada.
    """
    if policy.direction == "up":
        return observed > expected
    if policy.direction == "down":
        return observed < expected
    return observed != expected


def detect(
    facts: Iterable[Fact],
    baselines: Mapping[tuple[str, str, str, int], Baseline],
    catalog: Catalog,
    *,
    alpha: float = 0.20,
    min_samples: int = 12,
    z_threshold: float = 3.5,
) -> tuple[tuple[Anomaly, ...], dict[tuple[str, str, str, int], Baseline]]:
    """Detecta desvios nas métricas e calcula o próximo estado dos baselines.

    Os fatos de métrica são ordenados por instante causal. Cada observação é
    comparada ao baseline anterior da mesma fonte, entidade, métrica e hora
    local; somente depois dessa comparação o estado é atualizado. Fatos
    inválidos, sem política ou mais antigos que o baseline são ignorados.
    A entrada nunca é mutada.

    Args:
        facts: Fatos disponíveis na captura atual.
        baselines: Baselines anteriores indexados por fonte, entidade,
            métrica e hora de Brasília.
        catalog: Políticas de transformação e materialidade das métricas.
        alpha: Peso da observação nova na atualização EWMA.
        min_samples: Amostras mínimas antes de avaliar um desvio.
        z_threshold: Limite absoluto do z-score para considerar anomalia.

    Returns:
        Tupla com as anomalias detectadas e uma cópia atualizada dos
        baselines, sem alterar o mapeamento recebido.
    """
    state = {
        key: Baseline(value.mean, value.variance, value.n, value.last_event_at)
        for key, value in baselines.items()
    }
    anomalies: list[Anomaly] = []

    subjects = sorted(
        (f for f in facts if f.role == "subject" and f.kind == "metric"),
        key=lambda f: (f.event_start, f.source, f.entity, f.metric, f.fact_key),
    )
    for fact in subjects:
        if fact.value is None or not math.isfinite(fact.value):
            continue
        policy = catalog.metric(fact.metric)
        if policy is None:
            continue
        # O container roda em UTC; converter explicitamente sem depender do TZ
        # do processo.
        hour_brt = fact.event_start.astimezone(ZoneInfo("America/Sao_Paulo")).hour
        key = (fact.source, fact.entity, fact.metric, hour_brt)
        baseline = state.setdefault(key, Baseline())

        # Um update atrasado mais velho que o estado nao pode ser avaliado com
        # um baseline que ja contem o futuro dele. Ele permanece como contexto
        # para revisoes, mas nao inicia outra anomalia.
        if (
            baseline.last_event_at is not None
            and fact.event_start <= baseline.last_event_at
        ):
            continue

        transformed = _transform(fact.value, policy)
        old_mean = baseline.mean
        old_variance = baseline.variance
        if old_mean is not None and baseline.n >= min_samples:
            sigma = max(
                math.sqrt(max(old_variance or 0.0, 0.0)),
                policy.sigma_floor,
                0.05 * abs(old_mean),
            )
            z = (transformed - old_mean) / sigma
            expected = _inverse(old_mean, policy)
            if (
                abs(z) >= z_threshold
                and _bad_direction(fact.value, expected, policy)
                and _material(fact.value, expected, policy)
            ):
                direction = (
                    policy.direction
                    if policy.direction != "two_sided"
                    else ("up" if fact.value > expected else "down")
                )
                anomalies.append(
                    Anomaly(
                        fact=fact,
                        observed=fact.value,
                        expected=expected,
                        direction=direction,
                        deviation=fact.value - expected,
                        z=z,
                        strength=min(abs(z) / 6.0, 1.0),
                        baseline_snapshot={
                            "mean_transformed": old_mean,
                            "variance_transformed": old_variance,
                            "n": baseline.n,
                            "transform": policy.transform,
                            "sigma_effective": sigma,
                        },
                    )
                )

        if old_mean is None:
            baseline.mean = transformed
            baseline.variance = 0.0
        else:
            delta = transformed - old_mean
            baseline.mean = (1.0 - alpha) * old_mean + alpha * transformed
            baseline.variance = (1.0 - alpha) * (
                (old_variance or 0.0) + alpha * delta * delta
            )
        baseline.n += 1
        baseline.last_event_at = fact.event_start

    return tuple(anomalies), state
