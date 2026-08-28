"""Budgets por run, determinismo do corte e bordas do EWMA e do canario."""

from __future__ import annotations

import datetime as dt
import math
from itertools import count

import pytest

from argus_processing.catalog import Catalog
from argus_processing.detector import detect
from argus_processing.domain import Anomaly, Fact, SourceQuality
from argus_processing.quality import evaluate_quality
from argus_processing.rules import build_candidates, evaluate_candidates

NOW = dt.datetime(2026, 7, 12, 15, tzinfo=dt.UTC)
_IDS = count(1)


def _fact(
    source: str,
    entity: str,
    metric: str,
    value: float | None = 5,
    *,
    minutes: int = 0,
    sample_size: int | None = 1000,
    role: str = "subject",
) -> Fact:
    serial = next(_IDS)
    at = NOW + dt.timedelta(minutes=minutes)
    return Fact(
        fact_key=f"fact-{serial}",
        version_lsn=serial,
        role=role,
        kind="metric",
        event_start=at,
        event_end=None,
        available_at=at,
        source=source,
        entity=entity,
        metric=metric,
        dimension_type=None,
        dimension_value=None,
        value=value,
        sample_size=sample_size,
        attributes={},
    )


def _anomaly(fact: Fact, *, strength: float = 0.9) -> Anomaly:
    return Anomaly(
        fact=fact,
        observed=fact.value or 0,
        expected=1,
        direction="up",
        deviation=(fact.value or 0) - 1,
        z=5.4,
        strength=strength,
        baseline_snapshot={"n": 12},
    )


def _quality(source: str, status: str = "healthy", score: float = 1.0) -> SourceQuality:
    return SourceQuality(
        source=source,
        expected_cadence_seconds=900,
        last_observation_at=NOW,
        freshness=score,
        completeness=score,
        validity=1,
        consistency=1,
        quality_score=score,
        status=status,
        expected_buckets=1,
        observed_buckets=1,
        details={"evaluated_at": NOW.isoformat()},
    )


# --------------------------------------------------------------------------- #
# Budgets
# --------------------------------------------------------------------------- #


def _lote(quantidade: int) -> tuple[tuple[Anomaly, ...], tuple[Fact, ...]]:
    """`quantidade` anomalias internas distintas, cada uma com forca propria."""
    facts = tuple(
        _fact("newrelic", f"servico-{i:03d}", "error_rate_pct", 5 + i, minutes=i)
        for i in range(quantidade)
    )
    anomalies = tuple(
        _anomaly(fact, strength=0.10 + 0.8 * (i / quantidade))
        for i, fact in enumerate(facts)
    )
    return anomalies, facts


def test_budget_por_familia_trunca_e_conta_o_descarte():
    catalog = Catalog()
    anomalies, facts = _lote(40)
    qualities = (_quality("newrelic"),)
    candidates = [
        item
        for item in build_candidates(anomalies, facts, qualities, catalog)
        if item.family == "backend_internal"
    ]
    assert len(candidates) == 40

    _, prefiltered, evaluated, truncated = evaluate_candidates(
        candidates, anomalies, qualities, catalog, max_per_family=10
    )
    assert prefiltered == 40
    assert evaluated == 10
    assert truncated == 30


def test_budget_total_e_de_geracao_sao_independentes():
    catalog = Catalog()
    anomalies, facts = _lote(30)
    qualities = (_quality("newrelic"),)
    candidates = [
        item
        for item in build_candidates(anomalies, facts, qualities, catalog)
        if item.family == "backend_internal"
    ]

    # `max_total` corta ANTES da avaliacao.
    _, _, evaluated, truncated = evaluate_candidates(
        candidates, anomalies, qualities, catalog, max_total=12
    )
    assert evaluated == 12
    assert truncated == 18

    # `max_generated` corta DEPOIS: o candidato e avaliado e fica registrado,
    # mas nao vira hipotese publicavel.
    hypotheses, _, evaluated, _ = evaluate_candidates(
        candidates, anomalies, qualities, catalog, max_generated=5
    )
    assert evaluated == 30
    assert sum(h.evaluation_status == "generated" for h in hypotheses) == 5


def test_corte_e_estavel_por_forca_impacto_e_chave_canonica():
    """A ordem de entrada nao muda quem sobrevive ao budget."""
    catalog = Catalog()
    anomalies, facts = _lote(25)
    qualities = (_quality("newrelic"),)
    candidates = [
        item
        for item in build_candidates(anomalies, facts, qualities, catalog)
        if item.family == "backend_internal"
    ]

    direta, *_ = evaluate_candidates(
        candidates, anomalies, qualities, catalog, max_per_family=8
    )
    invertida, *_ = evaluate_candidates(
        list(reversed(candidates)), anomalies, qualities, catalog, max_per_family=8
    )
    assert [h.dedup_key for h in direta] == [h.dedup_key for h in invertida]
    assert [h.lineage_key for h in direta] == [h.lineage_key for h in invertida]
    assert [h.score for h in direta] == [h.score for h in invertida]

    # O corte fica com as anomalias mais fortes, e nao com as primeiras vistas.
    forcas = sorted((a.strength for a in anomalies), reverse=True)[:8]
    sobreviventes = {h.scope["service"] for h in direta}
    assert (
        sorted(
            (a.strength for a in anomalies if a.fact.entity in sobreviventes),
            reverse=True,
        )
        == forcas
    )


# --------------------------------------------------------------------------- #
# Detector: bordas do EWMA
# --------------------------------------------------------------------------- #


# O baseline e circadiano: uma serie por hora BRT. Aquecer um slot exige
# observacoes na MESMA hora do dia, e nao buckets consecutivos -- 12 buckets de
# 15 min cairiam espalhados em quatro slots com tres amostras cada.
UM_DIA = 24 * 60


def _serie(valores: list[float], *, metric: str = "latency_ms_avg") -> list[Fact]:
    return [
        _fact("prometheus", "playback", metric, valor, minutes=UM_DIA * i)
        for i, valor in enumerate(valores)
    ]


def _proximo(valor: float, dias: int = 12, *, metric: str = "latency_ms_avg") -> Fact:
    """Observacao seguinte no mesmo slot circadiano ja aquecido."""
    return _fact("prometheus", "playback", metric, valor, minutes=UM_DIA * dias)


def _aquecer(valor: float, n: int = 12, *, metric: str = "latency_ms_avg"):
    """Estado com `n` observacoes identicas: media estavel e variancia zero."""
    catalog = Catalog()
    facts = _serie([valor] * n, metric=metric)
    _, estado = detect(facts, {}, catalog)
    return catalog, estado


def test_variancia_zero_usa_piso_de_sigma_e_nao_divide_por_zero():
    """Serie constante tem variancia 0; o piso impede z infinito."""
    catalog, estado = _aquecer(100.0)
    chave = next(iter(estado))
    # A recorrencia do EWMA sobre valores identicos converge para zero, mas
    # em ponto flutuante para em ~1e-31: o que importa e que sqrt(variancia)
    # fica muito abaixo do piso de sigma da metrica.
    assert estado[chave].variance == pytest.approx(0.0, abs=1e-25)
    assert estado[chave].n == 12

    # Um valor identico nao pode gerar anomalia (z finito, desvio nulo).
    igual = [_proximo(100.0)]
    anomalias, _ = detect(igual, estado, catalog)
    assert anomalias == ()

    # Um salto real gera anomalia com z finito, apesar da variancia zero.
    salto = [_proximo(900.0)]
    anomalias, _ = detect(salto, estado, catalog)
    assert len(anomalias) == 1
    assert math.isfinite(anomalias[0].z)
    assert anomalias[0].baseline_snapshot["sigma_effective"] > 0


def test_transformacao_log1p_para_latencia_e_escala_original_para_apdex():
    catalog, estado_latencia = _aquecer(100.0)
    chave = next(iter(estado_latencia))
    # Latencia e contagem viajam em log1p; a media guardada e a transformada.
    assert estado_latencia[chave].mean == pytest.approx(math.log1p(100.0))
    salto = [_proximo(900.0)]
    anomalias, _ = detect(salto, estado_latencia, catalog)
    # O esperado devolvido ao usuario volta para a escala original.
    assert anomalias[0].expected == pytest.approx(100.0)

    # Apdex e taxa: fica na escala original.
    _, estado_apdex = _aquecer(0.95, metric="apdex")
    chave_apdex = next(iter(estado_apdex))
    assert estado_apdex[chave_apdex].mean == pytest.approx(0.95)


def test_direcao_da_metrica_ignora_melhora_e_apdex_cai_para_virar_anomalia():
    catalog, estado = _aquecer(0.95, metric="apdex")
    # Apdex e `direction=down`: subir e melhora, nao incidente.
    melhora = [_proximo(0.99, metric="apdex")]
    assert detect(melhora, estado, catalog)[0] == ()

    # Queda de 0,05 absoluto e a materialidade minima do Apdex.
    queda = [_proximo(0.40, metric="apdex")]
    anomalias, _ = detect(queda, estado, catalog)
    assert len(anomalias) == 1
    assert anomalias[0].direction == "down"


def test_materialidade_barra_desvio_estatistico_porem_irrelevante():
    """z alto nao basta: taxa precisa de 0,5 pp e 25% relativo."""
    catalog, estado = _aquecer(1.0, metric="error_rate_pct")
    chave = next(iter(estado))
    assert estado[chave].variance == pytest.approx(0.0, abs=1e-25)

    # +0,3 pp: relativamente grande (30%), mas abaixo do piso absoluto.
    pequeno = [_proximo(1.3, metric="error_rate_pct")]
    assert detect(pequeno, estado, catalog)[0] == ()

    # +2 pp: passa nos dois criterios.
    grande = [_proximo(3.0, metric="error_rate_pct")]
    assert len(detect(grande, estado, catalog)[0]) == 1


def test_cold_start_nao_gera_anomalia_antes_de_doze_observacoes():
    catalog = Catalog()
    # 11 observacoes de aquecimento e um salto na 12a: ainda em warmup.
    facts = _serie([100.0] * 11 + [5000.0])
    anomalias, estado = detect(facts, {}, catalog)
    assert anomalias == ()
    assert estado[next(iter(estado))].n == 12


def test_update_atrasado_nao_reavalia_com_baseline_que_ja_contem_o_futuro():
    catalog, estado = _aquecer(100.0)
    ultimo = estado[next(iter(estado))].last_event_at
    assert ultimo is not None
    # Um bucket ANTERIOR ao estado nao pode iniciar outra anomalia.
    atrasado = [
        _fact("prometheus", "playback", "latency_ms_avg", 9000.0, minutes=-UM_DIA)
    ]
    anomalias, novo = detect(atrasado, estado, catalog)
    assert anomalias == ()
    assert novo[next(iter(novo))].last_event_at == ultimo


# --------------------------------------------------------------------------- #
# Canario
# --------------------------------------------------------------------------- #


def _canario(facts, *, window_minutes: int = 60, simulator_end=None):
    catalog = Catalog()
    return {
        item.source: item
        for item in evaluate_quality(
            tuple(facts),
            catalog,
            window_start=NOW,
            window_end=NOW + dt.timedelta(minutes=window_minutes),
            simulator_end=simulator_end,
        )
    }


def test_qualidade_classifica_por_cadencia_saudavel_atrasada_e_silenciosa():
    # Prometheus tem cadencia de 900 s: 4 buckets numa janela de 60 min.
    completo = [
        _fact("prometheus", "playback", "latency_ms_avg", 100, minutes=15 * i)
        for i in range(4)
    ]
    saudavel = _canario(completo)["prometheus"]
    assert saudavel.status == "healthy"
    assert saudavel.completeness == 1.0
    assert saudavel.expected_buckets == 4

    # So o primeiro bucket: o ultimo dado ficou 3 cadencias para tras.
    atrasado = _canario(completo[:1])["prometheus"]
    assert atrasado.status in {"delayed", "incomplete"}
    assert atrasado.completeness < 1.0

    # Fonte sem nenhum fato na janela e silenciosa.
    silenciosa = _canario(completo)["apollo"]
    assert silenciosa.status == "silent"
    assert silenciosa.freshness == 0.0


def test_atraso_estrutural_da_npaw_nao_e_punido_como_silencio():
    """A NPAW e avaliada por `available_at`, nao por `event_start`."""
    # Evento de 28 h atras, porem disponivel agora: freshness intacta.
    antigo = Fact(
        fact_key="npaw-1",
        version_lsn=1,
        role="subject",
        kind="metric",
        event_start=NOW - dt.timedelta(hours=28),
        event_end=None,
        available_at=NOW,
        source="npaw_player",
        entity="player-x",
        metric="error_rate_pct",
        dimension_type="player",
        dimension_value="player-x",
        value=2.0,
        sample_size=500,
        attributes={},
    )
    npaw = _canario([antigo], window_minutes=60)["npaw_player"]
    assert npaw.status != "silent"
    assert npaw.freshness == 1.0
    assert npaw.last_observation_at == NOW - dt.timedelta(hours=28)


def test_fim_congelado_do_simulador_nao_cria_silencio_artificial():
    """Depois de `t1` nao ha dado a esperar, entao nao ha atraso a reportar."""
    facts = [_fact("prometheus", "playback", "latency_ms_avg", 100, minutes=0)]
    fim = NOW + dt.timedelta(minutes=15)
    congelado = _canario(facts, window_minutes=600, simulator_end=fim)["prometheus"]
    assert congelado.status == "healthy"
    assert congelado.completeness == 1.0

    # Sem o fim do simulador, a mesma janela longa acusaria silencio.
    aberto = _canario(facts, window_minutes=600)["prometheus"]
    assert aberto.status in {"silent", "incomplete"}
    assert aberto.completeness < 0.70


def test_valor_invalido_derruba_validity_e_marca_a_fonte():
    facts = [
        _fact("prometheus", "playback", "latency_ms_avg", 100, minutes=0),
        _fact("prometheus", "playback", "latency_ms_avg", None, minutes=15),
    ]
    invalida = _canario(facts, window_minutes=30)["prometheus"]
    assert invalida.validity < 0.99
    assert invalida.status == "invalid"
