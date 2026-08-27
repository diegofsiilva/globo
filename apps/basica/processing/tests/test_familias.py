"""As onze familias em quatro cenarios cada: positivo, contraditorio,
indisponivel e semanticamente nao relacionado.

O plano pede explicitamente os quatro recortes para CADA familia. Eles nao caem
todos no mesmo estado final, e essa e a propriedade sob teste:

- positivo              -> `generated`
- contraditorio         -> `discarded` (X >= 0,80) ou especificidade reduzida
- indisponivel          -> `insufficient_evidence`, ou cobertura menor SEM virar
                           contradicao (dado ausente nunca contraria)
- nao relacionado       -> candidato nem chega a se formar

Quando a familia nao define evidencia obrigatoria, "indisponivel" e verificado
pela regra do plano que a substitui: a feature entra como `unavailable`, a
cobertura cai e a contradicao permanece zero.
"""

from __future__ import annotations

import datetime as dt
from itertools import count

from argus_processing.catalog import Catalog
from argus_processing.domain import Anomaly, Fact, SourceQuality
from argus_processing.rules import build_candidates, evaluate_candidates

NOW = dt.datetime(2026, 7, 12, 15, tzinfo=dt.UTC)
_IDS = count(1)


def _fact(
    source: str,
    entity: str,
    metric: str,
    value: float = 5,
    *,
    minutes: int = 0,
    sample_size: int | None = 1000,
    dimension_type: str | None = None,
    dimension_value: str | None = None,
    kind: str = "metric",
    event_end: dt.datetime | None = None,
    attributes: dict | None = None,
) -> Fact:
    serial = next(_IDS)
    at = NOW + dt.timedelta(minutes=minutes)
    return Fact(
        fact_key=f"fact-{serial}",
        version_lsn=serial,
        role="subject" if kind == "metric" else "context",
        kind=kind,
        event_start=at,
        event_end=event_end,
        available_at=at,
        source=source,
        entity=entity,
        metric=metric,
        dimension_type=dimension_type,
        dimension_value=dimension_value,
        value=value,
        sample_size=sample_size,
        attributes=attributes or {},
    )


def _anomaly(fact: Fact, *, direction: str = "up", strength: float = 0.9) -> Anomaly:
    return Anomaly(
        fact=fact,
        observed=fact.value or 0,
        expected=1,
        direction=direction,
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
        observed_buckets=0 if status == "silent" else 1,
        details={"evaluated_at": NOW.isoformat()},
    )


def _run(
    family: str,
    anomalies: tuple[Anomaly, ...],
    facts: tuple[Fact, ...],
    extra_quality: tuple[SourceQuality, ...] = (),
):
    """Avalia so a familia pedida, com canario saudavel para toda fonte vista."""
    catalog = Catalog()
    sources = {fact.source for fact in facts} | {a.fact.source for a in anomalies}
    declared = {item.source for item in extra_quality}
    qualities = extra_quality + tuple(
        _quality(source) for source in sorted(sources - declared)
    )
    candidates = [
        item
        for item in build_candidates(anomalies, facts, qualities, catalog)
        if item.family == family
    ]
    hypotheses, *_ = evaluate_candidates(candidates, anomalies, qualities, catalog)
    return candidates, hypotheses


def _feature(hypothesis, name: str):
    return next(item for item in hypothesis.features if item.name == name)


# --------------------------------------------------------------------------- #
# 1. Regressao depois de deploy
# --------------------------------------------------------------------------- #


def test_deploy_regression():
    efeito = _fact("newrelic", "playback", "error_rate_pct")
    deploy = _fact("tsuru", "playback-api", "app.deploy", minutes=-5, kind="context")

    _, positivo = _run("deploy_regression", (_anomaly(efeito),), (efeito, deploy))
    assert positivo[0].evaluation_status == "generated"
    # A proximidade entra como meia-vida de 15 min, e nao como bonus fixo.
    assert _feature(positivo[0], "T").value == 2 ** (-5 / 15)

    # Contraditorio: a causa nao pode suceder o inicio do efeito.
    depois = _fact("tsuru", "playback-api", "app.deploy", minutes=5, kind="context")
    candidatos, _ = _run("deploy_regression", (_anomaly(efeito),), (efeito, depois))
    assert candidatos == []

    # Indisponivel: `autoscale.run` nunca e causa automatica.
    autoscale = _fact(
        "tsuru", "playback-api", "autoscale.run", minutes=-5, kind="context"
    )
    candidatos, _ = _run("deploy_regression", (_anomaly(efeito),), (efeito, autoscale))
    assert candidatos == []

    # Nao relacionado: deploy de outro servico nao explica este alvo.
    outro = _fact("tsuru", "billing", "app.deploy", minutes=-5, kind="context")
    candidatos, _ = _run("deploy_regression", (_anomaly(efeito),), (efeito, outro))
    assert candidatos == []


# --------------------------------------------------------------------------- #
# 2. Falha interna de backend
# --------------------------------------------------------------------------- #


def test_backend_internal():
    subject = _fact("newrelic", "playback", "error_rate_pct")
    apoio = _fact("apollo", "playback", "error_rate_pct", minutes=-2)

    _, positivo = _run("backend_internal", (_anomaly(subject),), (subject, apoio))
    assert positivo[0].evaluation_status == "generated"
    assert _feature(positivo[0], "C").applicability == "available"

    # Contraditorio: 4xx de RPaaS isolado e estrutural, nao incidente interno.
    rpaas = _fact("rpaas", "playback.video.globo.com", "4xx_rate_pct", sample_size=100)
    _, contra = _run("backend_internal", (_anomaly(rpaas),), (rpaas,))
    assert contra[0].evaluation_status == "discarded"
    assert contra[0].contradiction_strength >= 0.80

    # Indisponivel: sem fonte independente a cobertura cai, mas nada contraria.
    _, sozinho = _run("backend_internal", (_anomaly(subject),), (subject,))
    assert sozinho[0].evaluation_status == "generated"
    assert _feature(sozinho[0], "C").applicability == "unavailable"
    assert sozinho[0].contradiction_strength == 0
    assert sozinho[0].coverage < positivo[0].coverage

    # Nao relacionado: sinal interno de outro servico nao corrobora este.
    alheio = _fact("apollo", "billing", "error_rate_pct", minutes=-2)
    _, distante = _run("backend_internal", (_anomaly(subject),), (subject, alheio))
    assert _feature(distante[0], "C").applicability == "unavailable"


# --------------------------------------------------------------------------- #
# 3. Playback / autorizacao
# --------------------------------------------------------------------------- #


def test_playback_authorization():
    vhost = _fact("rpaas", "playback.video.globo.com", "4xx_rate_pct", sample_size=500)
    _, positivo = _run("playback_authorization", (_anomaly(vhost),), (vhost,))
    assert positivo[0].evaluation_status == "generated"

    # Contraditorio: 4xx e estruturalmente alto fora dos vhosts catalogados.
    fora = _fact("rpaas", "outro.video.globo.com", "4xx_rate_pct", sample_size=500)
    candidatos, _ = _run("playback_authorization", (_anomaly(fora),), (fora,))
    assert candidatos == []

    # Indisponivel: taxa sem as 100 requisicoes minimas nao sustenta a familia.
    magro = _fact("rpaas", "playback.video.globo.com", "4xx_rate_pct", sample_size=50)
    _, escasso = _run("playback_authorization", (_anomaly(magro),), (magro,))
    assert escasso[0].evaluation_status == "insufficient_evidence"
    assert escasso[0].contradiction_strength == 0

    # Nao relacionado: categoria desconhecida nao forma escopo. O par com
    # "acesso" e o controle -- sem ele o assert vazio passaria por engano, ja
    # que provaria apenas que a categoria nunca dispara a familia.
    def _categoria(valor: str) -> Fact:
        return _fact(
            "npaw_error_category",
            "playback",
            "error_rate_pct",
            dimension_type="categoria",
            dimension_value=valor,
        )

    acesso = _categoria("acesso")
    candidatos, _ = _run("playback_authorization", (_anomaly(acesso),), (acesso,))
    assert len(candidatos) == 1

    desconhecida = _categoria("?")
    candidatos, _ = _run(
        "playback_authorization", (_anomaly(desconhecida),), (desconhecida,)
    )
    assert candidatos == []


# --------------------------------------------------------------------------- #
# 4. Degradacao de CDN
# --------------------------------------------------------------------------- #


def test_cdn_degradation():
    cdn = _fact("cdn_live_errors", "globo-rj", "errors")
    qoe = _fact("npaw_live_qoe", "globo-rj", "jointime_s_avg", 8, minutes=5)

    _, positivo = _run("cdn_degradation", (_anomaly(cdn),), (cdn, qoe))
    assert positivo[0].evaluation_status == "generated"
    assert _feature(positivo[0], "E").value == 1.0

    # Contraditorio: origem degradando antes reduz a especificidade da CDN.
    origem = _fact("origin_live_errors", "globo-rj", "errors", minutes=-10)
    _, com_origem = _run(
        "cdn_degradation", (_anomaly(cdn), _anomaly(origem)), (cdn, origem, qoe)
    )
    assert _feature(com_origem[0], "E").value == 0.5
    assert com_origem[0].score < positivo[0].score

    # Indisponivel: sem QoE independente a cobertura cai sem contradicao.
    _, sem_qoe = _run("cdn_degradation", (_anomaly(cdn),), (cdn,))
    assert _feature(sem_qoe[0], "C").applicability == "unavailable"
    assert sem_qoe[0].contradiction_strength == 0

    # Nao relacionado: QoE de outro canal nao corrobora este.
    outro_canal = _fact("npaw_live_qoe", "globo-sp", "jointime_s_avg", 8, minutes=5)
    _, alheio = _run("cdn_degradation", (_anomaly(cdn),), (cdn, outro_canal))
    assert _feature(alheio[0], "C").applicability == "unavailable"


# --------------------------------------------------------------------------- #
# 5. Origem / encoding
# --------------------------------------------------------------------------- #


def test_origin_encoding():
    origem = _fact("origin_live_errors", "globo-rj", "errors")
    cdn_depois = _fact("cdn_live_errors", "globo-rj", "errors", minutes=10)

    _, positivo = _run("origin_encoding", (_anomaly(origem),), (origem, cdn_depois))
    assert positivo[0].evaluation_status == "generated"

    # Contraditorio: downstream anterior a origem inverte a causalidade.
    cdn_antes = _fact("cdn_live_errors", "globo-rj", "errors", minutes=-5)
    _, contra = _run(
        "origin_encoding", (_anomaly(origem), _anomaly(cdn_antes)), (origem, cdn_antes)
    )
    assert contra[0].evaluation_status == "discarded"
    assert contra[0].contradiction_strength >= 0.80

    # Indisponivel: sem efeito downstream a cobertura cai sem contradicao.
    _, sozinha = _run("origin_encoding", (_anomaly(origem),), (origem,))
    assert _feature(sozinha[0], "C").applicability == "unavailable"
    assert sozinha[0].contradiction_strength == 0

    # Nao relacionado: CDN de outro canal nao entra como efeito desta origem.
    outro = _fact("cdn_live_errors", "globo-sp", "errors", minutes=10)
    _, alheio = _run("origin_encoding", (_anomaly(origem),), (origem, outro))
    assert _feature(alheio[0], "C").applicability == "unavailable"


# --------------------------------------------------------------------------- #
# 6. Regional ou ISP (nunca a intersecao)
# --------------------------------------------------------------------------- #


def _geo(value: float, uf: str, sample: int, *, dimension_type: str = "uf") -> Fact:
    return _fact(
        "npaw_geo",
        uf,
        "error_rate_pct",
        value,
        sample_size=sample,
        dimension_type=dimension_type,
        dimension_value=uf,
    )


def test_regional_or_isp():
    rj = _geo(4, "RJ", 500)
    sp = _geo(1, "SP", 500)

    _, positivo = _run("regional_or_isp", (_anomaly(rj),), (rj, sp))
    assert positivo[0].evaluation_status == "generated"
    # UF e ISP sao escopos marginais separados: o escopo carrega UMA dimensao.
    assert positivo[0].scope == {"dimension_type": "uf", "dimension_value": "RJ"}

    # A dimensao ISP forma o seu proprio candidato, nunca um cruzamento.
    isp = _geo(4, "vivo", 500, dimension_type="isp")
    isp_par = _geo(1, "claro", 500, dimension_type="isp")
    candidatos, _ = _run("regional_or_isp", (_anomaly(isp),), (isp, isp_par))
    assert [item.scope["dimension_type"] for item in candidatos] == ["isp"]

    # Contraditorio: degradacao global equivalente nao e concentracao regional.
    sp_igual = _geo(4, "SP", 500)
    _, global_ = _run("regional_or_isp", (_anomaly(rj),), (rj, sp_igual))
    assert global_[0].evaluation_status == "insufficient_evidence"
    assert global_[0].contradiction_strength == 0

    # Indisponivel: sem as 500 sessoes do recorte.
    magro = _geo(4, "RJ", 100)
    _, escasso = _run("regional_or_isp", (_anomaly(magro),), (magro, sp))
    assert escasso[0].evaluation_status == "insufficient_evidence"

    # Nao relacionado: valor desconhecido nao forma escopo.
    desconhecido = _geo(4, "?", 500)
    candidatos, _ = _run("regional_or_isp", (_anomaly(desconhecido),), (desconhecido,))
    assert candidatos == []


# --------------------------------------------------------------------------- #
# 7. Bloqueio de WAF
# --------------------------------------------------------------------------- #


def test_waf_block():
    waf = _fact("cloudarmor", "playback", "blocked_rps", 100)
    efeito = _fact("prometheus", "playback", "error_rate_pct", minutes=5)

    _, positivo = _run("waf_block", (_anomaly(waf),), (waf, efeito))
    assert positivo[0].evaluation_status == "generated"

    # Contraditorio: problema anterior ao bloqueio contradiz a causalidade.
    antes = _fact("prometheus", "playback", "error_rate_pct", minutes=-5)
    _, contra = _run("waf_block", (_anomaly(waf), _anomaly(antes)), (waf, antes))
    assert contra[0].evaluation_status == "discarded"
    assert contra[0].contradiction_strength >= 0.80

    # Indisponivel: sem aplicacao protegida relacionada a cobertura cai.
    _, sozinho = _run("waf_block", (_anomaly(waf),), (waf,))
    assert _feature(sozinho[0], "C").applicability == "unavailable"
    assert sozinho[0].contradiction_strength == 0

    # Nao relacionado: erro de outra aplicacao nao mapeia para este bloqueio.
    alheio = _fact("prometheus", "billing", "error_rate_pct", minutes=5)
    _, distante = _run("waf_block", (_anomaly(waf),), (waf, alheio))
    assert _feature(distante[0], "C").applicability == "unavailable"


# --------------------------------------------------------------------------- #
# 8. Player ou dispositivo
# --------------------------------------------------------------------------- #


def _player(value: float, entity: str, sample: int, source: str = "npaw_player") -> Fact:
    return _fact(
        source,
        entity,
        "error_rate_pct",
        value,
        sample_size=sample,
        dimension_type="player" if source == "npaw_player" else "device",
        dimension_value=entity,
    )


def test_player_or_device():
    ruim = _player(4, "player-bad", 200)
    par = _player(1, "player-ok", 200)

    _, positivo = _run("player_or_device", (_anomaly(ruim),), (ruim, par))
    assert positivo[0].evaluation_status == "generated"

    # Contraditorio: pares igualmente degradados nao sustentam concentracao.
    par_ruim = _player(4, "player-ok", 200)
    _, global_ = _run("player_or_device", (_anomaly(ruim),), (ruim, par_ruim))
    assert global_[0].evaluation_status == "insufficient_evidence"
    assert global_[0].contradiction_strength == 0

    # Indisponivel: sem as 200 sessoes do segmento.
    magro = _player(4, "player-bad", 100)
    _, escasso = _run("player_or_device", (_anomaly(magro),), (magro, par))
    assert escasso[0].evaluation_status == "insufficient_evidence"

    # Nao relacionado: player e dispositivo permanecem dimensoes separadas --
    # um device saudavel nao serve de par para um player.
    device = _player(1, "device-ok", 200, source="npaw_device")
    candidatos, _ = _run("player_or_device", (_anomaly(ruim),), (ruim, device))
    assert len(candidatos) == 1
    assert candidatos[0].supporting == ()


# --------------------------------------------------------------------------- #
# 9. QoE sem erro explicito
# --------------------------------------------------------------------------- #


def test_qoe_without_error():
    qoe = _fact("prometheus", "playback", "latency_ms_avg", 300)
    erro_normal = _fact("apollo", "playback", "error_rate_pct", 0.1)

    _, positivo = _run("qoe_without_error", (_anomaly(qoe),), (qoe, erro_normal))
    assert positivo[0].evaluation_status == "generated"

    # Contraditorio: se o erro tambem esta anomalo, nao e "QoE sem erro".
    _, com_erro = _run(
        "qoe_without_error",
        (_anomaly(qoe), _anomaly(erro_normal)),
        (qoe, erro_normal),
    )
    assert com_erro[0].evaluation_status == "insufficient_evidence"

    # Indisponivel: erro ausente gera insufficient, nunca "sem erro".
    _, sem_erro = _run("qoe_without_error", (_anomaly(qoe),), (qoe,))
    assert sem_erro[0].evaluation_status == "insufficient_evidence"
    assert sem_erro[0].contradiction_strength == 0

    # Nao relacionado: erro normal de outro servico nao prova nada aqui.
    alheio = _fact("apollo", "billing", "error_rate_pct", 0.1)
    _, distante = _run("qoe_without_error", (_anomaly(qoe),), (qoe, alheio))
    assert distante[0].evaluation_status == "insufficient_evidence"


# --------------------------------------------------------------------------- #
# 10. Pico esperado em evento ao vivo
# --------------------------------------------------------------------------- #


def test_expected_live_peak():
    volume = _fact("npaw_live_active", "globo-rj", "active_sessions", 5000)
    evento = _fact(
        "editorial",
        "globo",
        "live_event",
        kind="context",
        event_end=NOW + dt.timedelta(hours=2),
    )
    erro_normal = _fact("apollo", "globo-rj", "error_rate_pct", 0.1)
    qoe_normal = _fact("npaw_live_qoe", "globo-rj", "jointime_s_avg", 1)

    _, positivo = _run(
        "expected_live_peak",
        (_anomaly(volume),),
        (volume, evento, erro_normal, qoe_normal),
    )
    assert positivo[0].evaluation_status == "generated"
    # Pico esperado e contexto, nunca incidente operacional.
    assert positivo[0].kind == "context"

    # Contraditorio: se a experiencia piorou, o evento nao explica o pico.
    qoe_ruim = _fact("npaw_live_qoe", "globo-rj", "jointime_s_avg", 8)
    _, contra = _run(
        "expected_live_peak",
        (_anomaly(volume), _anomaly(qoe_ruim)),
        (volume, evento, qoe_ruim, erro_normal),
    )
    assert contra[0].evaluation_status == "discarded"

    # Indisponivel: sem erro e QoE normais nao da para afirmar normalidade.
    _, sem_controle = _run("expected_live_peak", (_anomaly(volume),), (volume, evento))
    assert sem_controle[0].evaluation_status == "insufficient_evidence"
    assert sem_controle[0].contradiction_strength == 0

    # Nao relacionado: evento de outro canal nao cobre este volume.
    outro_evento = _fact(
        "editorial",
        "esporte",
        "live_event",
        kind="context",
        event_end=NOW + dt.timedelta(hours=2),
    )
    candidatos, _ = _run(
        "expected_live_peak",
        (_anomaly(volume),),
        (volume, outro_evento, erro_normal, qoe_normal),
    )
    assert candidatos == []


# --------------------------------------------------------------------------- #
# 11. Atraso / falha da fonte
# --------------------------------------------------------------------------- #


def test_source_data_delay():
    silenciosa = _quality("prometheus", "silent", 0.0)
    _, positivo = _run("source_data_delay", (), (), (silenciosa,))
    assert positivo[0].evaluation_status == "generated"
    # Fonte ruim vira hipotese de dados, nunca queda operacional.
    assert positivo[0].kind == "data_quality"
    assert positivo[0].scope == {"source": "prometheus"}
    # Sem evento causal identificavel, a proximidade sai do denominador.
    assert _feature(positivo[0], "T").applicability == "not_applicable"

    # Os quatro estados degradados abrem finding de qualidade.
    for status in ("delayed", "incomplete", "silent", "invalid"):
        candidatos, _ = _run(
            "source_data_delay", (), (), (_quality("apollo", status, 0.2),)
        )
        assert len(candidatos) == 1, status

    # Indisponivel/nao relacionado: fonte saudavel nao gera finding algum.
    candidatos, _ = _run("source_data_delay", (), (), (_quality("apollo", "healthy"),))
    assert candidatos == []


def test_fontes_simetricas_nao_geram_dedup_key_duplicada():
    """Regressao: duas fontes internas que se corroboram colidiam na chave.

    `prometheus` e `apollo` reportando a mesma metrica, no mesmo servico e na
    mesma hora produzem candidatos simetricos -- o subject de um e o supporting
    do outro. Como `dedup_key` cobre familia + escopo + periodo + conjunto de
    fatos (e nao quem e o subject), os dois saiam com a chave identica e o
    commit morria em UNIQUE (run_id, dedup_key). Foi exatamente o que derrubou
    o primeiro run real na AWS.
    """
    prometheus = _fact("prometheus", "playback", "error_rate_pct", 9.0)
    apollo = _fact("apollo", "playback", "error_rate_pct", 7.5)

    candidatos, hipoteses = _run(
        "backend_internal",
        (_anomaly(prometheus), _anomaly(apollo)),
        (prometheus, apollo),
    )
    # Os dois candidatos continuam sendo formados...
    assert len(candidatos) == 2
    # ...mas so um sobrevive por chave: o commit precisa de dedup_key unica.
    chaves = [h.dedup_key for h in hipoteses]
    assert len(chaves) == len(set(chaves))
    assert len(hipoteses) == 1
    assert hipoteses[0].evaluation_status == "generated"
