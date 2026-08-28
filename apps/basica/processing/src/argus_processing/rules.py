"""Onze familias deterministicas de hipoteses."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from argus_processing.catalog import Catalog
from argus_processing.domain import Anomaly, Evidence, Fact, Hypothesis, SourceQuality
from argus_processing.scoring import score_features

INTERNAL_SOURCES = {"newrelic", "apollo", "prometheus", "rpaas"}
QOE_TOKENS = ("jointime", "buffer", "stall", "latency", "dropped")
VOLUME_METRICS = {"sessions", "active_sessions", "requests_total", "rpm", "throughput"}


def canonical_hash(value: Any) -> str:
    """Hash estavel de uma estrutura, para deduplicacao e linhagem.

    `sort_keys=True` e o que torna o hash estavel: sem isso, dois dicionarios
    com o mesmo conteudo em ordem diferente produziriam hashes diferentes, e a
    mesma hipotese reemitida no ciclo seguinte apareceria como nova. Ordem de
    dicionario nao pode influir em nada aqui (AGENTS.md, regra 1).

    Args:
        value (Any): Estrutura serializavel. `default=str` cobre `datetime` e
            os tipos do psycopg.

    Returns:
        str: SHA-256 em hexadecimal.
    """
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _within(left: dt.datetime, right: dt.datetime, minutes: int) -> bool:
    """Diz se dois instantes estao dentro da mesma janela de correlacao.

    Simetrico (usa valor absoluto): a janela vale nos dois sentidos porque a
    ordem de chegada nao e a ordem dos eventos -- fontes tem latencias
    diferentes, e o `available_at` da NPAW fica 28 h atras do Prometheus.

    Args:
        left (datetime): Um instante.
        right (datetime): O outro.
        minutes (int): Meia-largura da janela, em minutos.

    Returns:
        bool: `True` quando a distancia cabe na janela.
    """
    return abs((left - right).total_seconds()) <= minutes * 60


def _is_qoe(metric: str) -> bool:
    """Diz se a metrica mede qualidade de experiencia do espectador.

    Args:
        metric (str): Nome da metrica.

    Returns:
        bool: `True` para tempo de inicio, buffer, travamento, latencia e
            quadros descartados -- o que o espectador sente, por oposicao ao
            que so aparece no grafico de infraestrutura.
    """
    lower = metric.lower()
    return any(token in lower for token in QOE_TOKENS)


def _is_error(metric: str) -> bool:
    """Diz se a metrica conta falhas.

    Args:
        metric (str): Nome da metrica.

    Returns:
        bool: `True` para metricas de erro e de familias 4xx/5xx.
    """
    lower = metric.lower()
    return "error" in lower or "4xx" in lower or "5xx" in lower


def _source_quality(source: str, quality: Mapping[str, SourceQuality]) -> float | None:
    """Score de qualidade de uma fonte no ciclo.

    Args:
        source (str): Nome da fonte.
        quality (Mapping[str, SourceQuality]): Vereditos do canario, por fonte.

    Returns:
        float | None: O score, ou `None` quando a fonte nao foi avaliada. `None`
            e diferente de `0.0`: zero significa "avaliada e ruim", e ausencia
            significa "nao ha o que dizer" -- tratar os dois igual faria o motor
            penalizar uma hipotese por falta de informacao sobre ela.
    """
    item = quality.get(source)
    return item.quality_score if item else None


def _corroboration(
    facts: Iterable[Fact],
    subject: Fact | None,
    anomalies: tuple[Anomaly, ...],
    catalog: Catalog,
    quality: Mapping[str, SourceQuality],
    *,
    window_minutes: int,
) -> float | None:
    """Mede o quanto fontes INDEPENDENTES concordam com o mesmo sintoma.

    Duas fontes que leem do mesmo agente nao sao duas confirmacoes: elas erram
    juntas. Por isso o maximo e tomado por `independence_group` do catalogo, e
    nao por fonte -- caso contrario, adicionar uma quarta sonda ao mesmo coletor
    inflaria artificialmente a confianca da hipotese.

    A combinacao e "probabilidade de ao menos um" (1 - produto dos
    complementos), que satura suavemente: a terceira confirmacao independente
    soma menos que a segunda, o que e o comportamento desejado.

    Args:
        facts (Iterable[Fact]): Fatos candidatos a corroborar.
        subject (Fact | None): Fato central; usado para medir o alinhamento
            temporal. `None` desliga a atenuacao por distancia.
        anomalies (tuple[Anomaly, ...]): Anomalias do ciclo. Um fato que TAMBEM
            e anomalia corrobora com a forca dela; um fato normal corrobora com
            0.5, porque presenca de dado consistente e evidencia mais fraca que
            um desvio simultaneo.
        catalog (Catalog): De onde sai o grupo de independencia.
        quality (Mapping[str, SourceQuality]): Qualidade por fonte; uma fonte
            degradada corrobora menos.
        window_minutes (int): Janela de alinhamento temporal.

    Returns:
        float | None: Corroboracao em [0, 1], ou `None` quando nenhuma fonte
            avaliada tinha o que dizer.
    """
    anomaly_by_fact = {item.fact.fact_key: item for item in anomalies}
    strongest: dict[str, float] = {}
    for fact in facts:
        q = _source_quality(fact.source, quality)
        if q is None:
            continue
        finding = anomaly_by_fact.get(fact.fact_key)
        strength = finding.strength if finding else 0.5
        delta = (
            abs((fact.event_start - subject.event_start).total_seconds()) / 60
            if subject
            else 0.0
        )
        alignment = max(0.0, 1.0 - delta / max(1, window_minutes))
        group = catalog.source(fact.source)["independence_group"]
        strongest[group] = max(strongest.get(group, 0.0), strength * alignment * q)
    if not strongest:
        return None
    product = 1.0
    for strength in strongest.values():
        product *= 1.0 - strength
    return 1.0 - product


def _impact(fact: Fact) -> float | None:
    """Traduz o tamanho da amostra num fator de impacto em [0, 1].

    Logaritmico e nao linear: a diferenca entre 10 e 100 sessoes afetadas
    importa muito mais que entre 10.000 e 10.090. Com escala linear, so os
    maiores POPs jamais apareceriam no topo, e uma degradacao total num POP
    pequeno ficaria invisivel.

    Args:
        fact (Fact): Fato central da hipotese.

    Returns:
        float | None: O impacto normalizado, ou `None` quando a fonte nao
            informou tamanho de amostra.
    """
    if fact.sample_size is None:
        return None
    return min(1.0, math.log1p(fact.sample_size) / math.log1p(10_000))


@dataclass(frozen=True, slots=True)
class Candidate:
    """Uma hipotese ANTES da avaliacao: o formato, sem o score.

    Separar a geracao da avaliacao e o que permite contar quantos candidatos
    existiam antes de qualquer corte, e e essa contagem que distingue "nao ha
    hipotese" de "havia candidatos demais e o ciclo parou no teto".

    `required_missing` guarda o que a familia exigia e nao estava disponivel --
    e o que vira `Feature` com `applicability = "unavailable"`, em vez de zero.
    """

    family: str
    kind: str
    anomaly_index: int | None
    subject: Fact | None
    supporting: tuple[Fact, ...]
    required_missing: tuple[str, ...]
    contrary: tuple[Evidence, ...]
    scope: dict[str, Any]
    title: str
    summary: str
    temporal_score: float | None = None
    specificity: float | None = 1.0


def _facts_related(
    subject: Fact,
    facts: Iterable[Fact],
    catalog: Catalog,
    *,
    minutes: int,
    sources: set[str] | None = None,
    predicate=lambda _f: True,
) -> list[Fact]:
    """Fatos vizinhos de um sujeito, no tempo e no escopo.

    Args:
        subject (Fact): Fato central. Ele proprio nunca entra no resultado.
        facts (Iterable[Fact]): Universo de fatos do ciclo.
        catalog (Catalog): De onde sai a relacao entre entidades, que aceita
            tambem a hierarquia (um POP dentro do cluster que sofreu deploy).
        minutes (int): Meia-largura da janela temporal.
        sources (set[str] | None): Restringe as fontes; `None` aceita todas.
        predicate: Filtro adicional por fato.

    Returns:
        list[Fact]: Os fatos que satisfazem todas as condicoes.
    """
    return [
        fact
        for fact in facts
        if fact.fact_key != subject.fact_key
        and _within(fact.event_start, subject.event_start, minutes)
        and catalog.related(fact.entity, subject.entity)
        and (sources is None or fact.source in sources)
        and predicate(fact)
    ]


def build_candidates(
    anomalies: tuple[Anomaly, ...],
    facts: tuple[Fact, ...],
    qualities: tuple[SourceQuality, ...],
    catalog: Catalog,
) -> tuple[Candidate, ...]:
    """Gera os candidatos das 11 familias a partir das anomalias do ciclo.

    Args:
        anomalies (tuple[Anomaly, ...]): Anomalias detectadas.
        facts (tuple[Fact, ...]): Todos os fatos da janela, inclusive os
            normais -- um fato SEM desvio e evidencia contraria valida.
        qualities (tuple[SourceQuality, ...]): Veredito do canario por fonte.
        catalog (Catalog): Catalogos e parametros das familias.

    Returns:
        tuple[Candidate, ...]: Candidatos ainda sem score.
    """
    candidates: list[Candidate] = []
    anomalous_keys = {item.fact.fact_key for item in anomalies}
    for index, anomaly in enumerate(anomalies):
        subject = anomaly.fact
        metric = subject.metric.lower()
        source = subject.source

        # 1. Regressao depois de deploy.
        deploys = [
            f
            for f in facts
            if f.source == "tsuru"
            and f.metric == "app.deploy"
            and f.event_start <= subject.event_start
            and 0 <= (subject.event_start - f.event_start).total_seconds() <= 3600
            and catalog.related(f.entity, subject.entity)
        ]
        if deploys:
            deploy = max(deploys, key=lambda f: f.event_start)
            delta = (subject.event_start - deploy.event_start).total_seconds() / 60
            candidates.append(
                Candidate(
                    "deploy_regression",
                    "operational",
                    index,
                    subject,
                    (deploy,),
                    (),
                    (),
                    {"service": catalog.normalize_entity(subject.entity)},
                    f"Possível regressão após deploy em {subject.entity}",
                    "A degradação começou depois de um deploy "
                    "semanticamente relacionado.",
                    2 ** (-delta / 15),
                    1.0,
                )
            )

        # 2. Falha interna.
        if source in INTERNAL_SOURCES and (
            _is_error(metric)
            or "latency" in metric
            or metric == "apdex"
            or "response_time" in metric
        ):
            support = _facts_related(
                subject,
                facts,
                catalog,
                minutes=15,
                sources=INTERNAL_SOURCES,
                predicate=lambda f: (
                    _is_error(f.metric)
                    or "latency" in f.metric
                    or f.metric == "apdex"
                    or "response_time" in f.metric
                ),
            )
            contrary: tuple[Evidence, ...] = ()
            if source == "rpaas" and "4xx" in metric:
                contrary = (
                    Evidence(
                        "subject",
                        "contrary",
                        "4xx de RPaaS isolado pode ser comportamento estrutural",
                        subject,
                        anomaly.observed,
                        anomaly.expected,
                        0.9,
                    ),
                )
            candidates.append(
                Candidate(
                    "backend_internal",
                    "operational",
                    index,
                    subject,
                    tuple(support),
                    (),
                    contrary,
                    {"service": catalog.normalize_entity(subject.entity)},
                    f"Possível falha interna em {subject.entity}",
                    "Sinais internos indicam erro, latência ou queda "
                    "de saúde do serviço.",
                )
            )

        # 3. Playback/autorizacao.
        playback_trigger = (
            (
                source == "rpaas"
                and "4xx" in metric
                and catalog.playback_vhost(subject.entity)
            )
            or "startup_error" in metric
            or (source == "npaw_error_category" and subject.dimension_value == "acesso")
            or (
                source == "npaw_error_attr"
                and "author" in str(subject.attributes).lower()
            )
        )
        if playback_trigger:
            requires_sample = "rate" in metric or "4xx" in metric
            missing = (
                ("volume mínimo de 100 requisições/sessões",)
                if requires_sample and (subject.sample_size or 0) < 100
                else ()
            )
            support = _facts_related(
                subject,
                facts,
                catalog,
                minutes=30,
                predicate=lambda f: _is_error(f.metric),
            )
            candidates.append(
                Candidate(
                    "playback_authorization",
                    "operational",
                    index,
                    subject,
                    tuple(support),
                    missing,
                    (),
                    {"flow": "playback", "entity": subject.entity},
                    "Possível falha de playback ou autorização",
                    "Erros de acesso ou inicialização se concentram "
                    "no fluxo de playback.",
                )
            )

        # 4. CDN.
        if source.startswith("cdn_") or (
            source == "npaw_error_attr" and subject.attributes.get("cdn")
        ):
            support = _facts_related(
                subject,
                facts,
                catalog,
                minutes=30,
                predicate=lambda f: _is_qoe(f.metric),
            )
            origin_before = any(
                other.fact.source.startswith("origin_")
                and other.fact.event_start <= subject.event_start
                and _within(other.fact.event_start, subject.event_start, 30)
                and catalog.related(other.fact.entity, subject.entity)
                for other in anomalies
            )
            candidates.append(
                Candidate(
                    "cdn_degradation",
                    "operational",
                    index,
                    subject,
                    tuple(support),
                    (),
                    (),
                    {"channel": subject.entity},
                    "Possível degradação de CDN",
                    "Erros de entrega aparecem no mesmo canal da degradação observada.",
                    specificity=0.5 if origin_before else 1.0,
                )
            )

        # 5. Origem/encoding.
        origin_trigger = source.startswith("origin_") or (
            source == "npaw_error_category" and subject.dimension_value == "origem"
        )
        if origin_trigger:
            support = _facts_related(
                subject,
                facts,
                catalog,
                minutes=30,
                predicate=lambda f: f.source.startswith("cdn_") or _is_qoe(f.metric),
            )
            support = [f for f in support if f.event_start >= subject.event_start]
            downstream_before = [
                other
                for other in anomalies
                if other.fact.event_start < subject.event_start
                and _within(other.fact.event_start, subject.event_start, 30)
                and catalog.related(other.fact.entity, subject.entity)
                and (other.fact.source.startswith("cdn_") or _is_qoe(other.fact.metric))
            ]
            candidates.append(
                Candidate(
                    "origin_encoding",
                    "operational",
                    index,
                    subject,
                    tuple(support),
                    (),
                    tuple(
                        Evidence(
                            "supporting",
                            "contrary",
                            "efeito downstream começou antes da origem",
                            item.fact,
                            item.observed,
                            item.expected,
                            0.9,
                        )
                        for item in downstream_before
                    ),
                    {"channel": subject.entity},
                    "Possível falha de origem ou encoding",
                    "A origem degradou antes ou junto dos sinais "
                    "de entrega e experiência.",
                )
            )

        # 6. Regional ou ISP, nunca intersecao.
        if (
            source == "npaw_geo"
            and subject.dimension_type in {"uf", "isp"}
            and subject.dimension_value not in {None, "?", "(desconhecido)"}
        ):
            peers = [
                f
                for f in facts
                if f.source == source
                and f.metric == subject.metric
                and f.dimension_type == subject.dimension_type
                and f.dimension_value != subject.dimension_value
                and f.fact_key not in anomalous_keys
                and _within(f.event_start, subject.event_start, 60)
                and f.value is not None
            ]
            peer_mean = sum(f.value for f in peers) / len(peers) if peers else None
            lift = (
                subject.value / peer_mean
                if peer_mean and subject.value is not None
                else None
            )
            delta = (
                subject.value - peer_mean
                if peer_mean is not None and subject.value is not None
                else None
            )
            missing: list[str] = []
            if (subject.sample_size or 0) < 500:
                missing.append("500 sessões no segmento")
            if lift is None or lift < 2 or delta is None or delta < 1:
                missing.append("lift >= 2 e diferença >= 1 pp contra pares")
            candidates.append(
                Candidate(
                    "regional_or_isp",
                    "operational",
                    index,
                    subject,
                    tuple(peers),
                    tuple(missing),
                    (),
                    {
                        "dimension_type": subject.dimension_type,
                        "dimension_value": subject.dimension_value,
                    },
                    f"Possível degradação por {subject.dimension_type.upper()}",
                    "A degradação está concentrada em um recorte com volume material.",
                    specificity=min(1.0, (lift or 1.0) / 3.0),
                )
            )

        # 7. WAF.
        if source == "cloudarmor" and "blocked" in metric:
            support = _facts_related(
                subject,
                facts,
                catalog,
                minutes=15,
                predicate=lambda f: _is_error(f.metric) or "cpu" in f.metric.lower(),
            )
            support = [f for f in support if f.event_start >= subject.event_start]
            effect_before = [
                other
                for other in anomalies
                if other.fact.event_start < subject.event_start
                and _within(other.fact.event_start, subject.event_start, 15)
                and catalog.related(other.fact.entity, subject.entity)
                and (_is_error(other.fact.metric) or "cpu" in other.fact.metric.lower())
            ]
            candidates.append(
                Candidate(
                    "waf_block",
                    "operational",
                    index,
                    subject,
                    tuple(support),
                    (),
                    tuple(
                        Evidence(
                            "supporting",
                            "contrary",
                            "impacto começou antes do aumento de bloqueios",
                            item.fact,
                            item.observed,
                            item.expected,
                            0.9,
                        )
                        for item in effect_before
                    ),
                    {"application": catalog.normalize_entity(subject.entity)},
                    "Possível ataque ou bloqueio de WAF",
                    "O aumento de bloqueios antecede ou coincide "
                    "com impacto na aplicação.",
                )
            )

        # 8. Player/dispositivo.
        if source in {"npaw_player", "npaw_device", "npaw_player_live"}:
            peers = [
                f
                for f in facts
                if f.source == source
                and f.metric == subject.metric
                and f.entity != subject.entity
                and f.fact_key not in anomalous_keys
                and _within(f.event_start, subject.event_start, 60)
                and f.value is not None
            ]
            peer_mean = sum(f.value for f in peers) / len(peers) if peers else None
            lift = (
                subject.value / peer_mean
                if peer_mean and subject.value is not None
                else None
            )
            delta = (
                subject.value - peer_mean
                if peer_mean is not None and subject.value is not None
                else None
            )
            missing = []
            if (subject.sample_size or 0) < 200:
                missing.append("200 sessões no segmento")
            if lift is None or lift < 2 or delta is None or delta < 1:
                missing.append("lift >= 2 e diferença >= 1 pp contra pares")
            candidates.append(
                Candidate(
                    "player_or_device",
                    "operational",
                    index,
                    subject,
                    tuple(peers),
                    tuple(missing),
                    (),
                    {
                        "dimension_type": subject.dimension_type,
                        "dimension_value": subject.dimension_value,
                    },
                    "Possível regressão de player ou dispositivo",
                    "O efeito está concentrado em um segmento enquanto "
                    "os pares permanecem estáveis.",
                    specificity=min(1.0, (lift or 1.0) / 3.0),
                )
            )

        # 9. QoE sem erro explicito.
        if _is_qoe(metric):
            error_facts = _facts_related(
                subject,
                facts,
                catalog,
                minutes=60,
                predicate=lambda f: _is_error(f.metric),
            )
            error_anomalous_keys = {
                a.fact.fact_key for a in anomalies if _is_error(a.fact.metric)
            }
            normal_errors = [
                f for f in error_facts if f.fact_key not in error_anomalous_keys
            ]
            missing = () if normal_errors else ("métrica de erro disponível e normal",)
            candidates.append(
                Candidate(
                    "qoe_without_error",
                    "operational",
                    index,
                    subject,
                    tuple(normal_errors),
                    missing,
                    (),
                    {"entity": subject.entity},
                    "Possível degradação de QoE sem erro explícito",
                    "A experiência piorou sem aumento correspondente "
                    "das métricas de erro.",
                )
            )

        # 10. Pico esperado em evento ao vivo.
        if metric in VOLUME_METRICS and anomaly.direction == "up":
            events = [
                f
                for f in facts
                if f.source == "editorial"
                and f.metric == "live_event"
                and f.event_start <= subject.event_start <= (f.event_end or f.event_start)
                and catalog.related(f.entity, subject.entity)
            ]
            if events:
                bad_experience = [
                    a
                    for a in anomalies
                    if catalog.related(a.fact.entity, subject.entity)
                    and (_is_error(a.fact.metric) or _is_qoe(a.fact.metric))
                    and _within(a.fact.event_start, subject.event_start, 60)
                ]
                missing = (
                    ()
                    if not bad_experience
                    else ("erro e QoE precisam permanecer normais",)
                )
                contrary = tuple(
                    Evidence(
                        "supporting",
                        "contrary",
                        "experiência também degradou",
                        a.fact,
                        a.observed,
                        a.expected,
                        a.strength,
                    )
                    for a in bad_experience
                )
                related = [
                    f
                    for f in facts
                    if catalog.related(f.entity, subject.entity)
                    and _within(f.event_start, subject.event_start, 60)
                ]
                normal_error = any(
                    _is_error(f.metric) and f.fact_key not in anomalous_keys
                    for f in related
                )
                normal_qoe = any(
                    _is_qoe(f.metric) and f.fact_key not in anomalous_keys
                    for f in related
                )
                required = list(missing)
                if not normal_error:
                    required.append("métrica de erro disponível e normal")
                if not normal_qoe:
                    required.append("métrica de QoE disponível e normal")
                candidates.append(
                    Candidate(
                        "expected_live_peak",
                        "context",
                        index,
                        subject,
                        tuple(events),
                        tuple(required),
                        contrary,
                        {"channel": subject.entity},
                        "Pico esperado por evento ao vivo",
                        "O volume cresceu durante evento compatível "
                        "sem degradação de experiência.",
                    )
                )

    # 11. Qualidade de fonte nao depende de uma anomalia operacional.
    for item in qualities:
        if item.status not in {"delayed", "incomplete", "silent", "invalid"}:
            continue
        candidates.append(
            Candidate(
                "source_data_delay",
                "data_quality",
                None,
                None,
                (),
                (),
                (),
                {"source": item.source},
                f"Possível falha ou atraso da fonte {item.source}",
                f"O canário classificou a fonte como {item.status}; "
                "ausência não será tratada como incidente.",
                specificity=1.0,
            )
        )

    return tuple(candidates)


def evaluate_candidates(
    candidates: Iterable[Candidate],
    anomalies: tuple[Anomaly, ...],
    qualities: tuple[SourceQuality, ...],
    catalog: Catalog,
    *,
    max_total: int = 10_000,
    max_per_family: int = 2_000,
    max_generated: int = 500,
) -> tuple[tuple[Hypothesis, ...], int, int, int]:
    """Pontua os candidatos e devolve as hipoteses, com as contagens de corte.

    A ordenacao antes do corte e determinista ate o ultimo criterio: forca da
    anomalia, impacto, familia e, por fim, `canonical_hash` do proprio
    candidato. O hash como desempate final e o que garante que dois ciclos com
    a mesma entrada cortem exatamente os mesmos candidatos -- sem ele, a ordem
    dependeria da iteracao de dicionario e o resultado deixaria de ser
    reproduzivel (AGENTS.md, regra 1).

    Args:
        candidates (Iterable[Candidate]): Candidatos gerados.
        anomalies (tuple[Anomaly, ...]): Anomalias do ciclo, referenciadas por
            indice pelos candidatos.
        qualities (tuple[SourceQuality, ...]): Veredito do canario por fonte.
        catalog (Catalog): Pesos e parametros do score.
        max_total (int): Teto de candidatos avaliados no ciclo.
        max_per_family (int): Teto por familia, para que uma familia ruidosa
            nao consuma sozinha o orcamento das outras.
        max_generated (int): Teto de hipoteses publicadas.

    Returns:
        tuple[tuple[Hypothesis, ...], int, int, int]: As hipoteses e os tres
            contadores -- pre-filtrados, avaliados e truncados. Os contadores
            fazem parte do resultado, e nao do log: sem eles um ciclo truncado
            se apresentaria como um ciclo limpo.
    """
    quality = {item.source: item for item in qualities}
    ordered = sorted(
        candidates,
        key=lambda c: (
            -(
                anomalies[c.anomaly_index].strength
                if c.anomaly_index is not None
                else 1.0
            ),
            -(_impact(c.subject) or 0.0) if c.subject else 0.0,
            c.family,
            canonical_hash(
                {
                    "family": c.family,
                    "scope": c.scope,
                    "subject": c.subject.fact_key if c.subject else None,
                    "supporting": sorted(f.fact_key for f in c.supporting),
                }
            ),
        ),
    )
    per_family: dict[str, int] = defaultdict(int)
    selected: list[Candidate] = []
    truncated = 0
    for candidate in ordered:
        if len(selected) >= max_total or per_family[candidate.family] >= max_per_family:
            truncated += 1
            continue
        selected.append(candidate)
        per_family[candidate.family] += 1

    results: list[Hypothesis] = []
    generated = 0
    for candidate in selected:
        anomaly = (
            anomalies[candidate.anomaly_index]
            if candidate.anomaly_index is not None
            else None
        )
        subject = candidate.subject
        quality_item = quality.get(candidate.scope.get("source", ""))
        source_q = (
            _source_quality(subject.source, quality)
            if subject
            else (quality_item.quality_score if quality_item else None)
        )
        corroboration = _corroboration(
            candidate.supporting,
            subject,
            anomalies,
            catalog,
            quality,
            window_minutes=int(catalog.rule(candidate.family)["window_minutes"]),
        )
        contradiction = max((e.strength or 0.0 for e in candidate.contrary), default=0.0)
        values = {
            "A": ("available", anomaly.strength, "força do desvio causal")
            if anomaly
            else ("available", 1.0 - (source_q or 0.0), "severidade do canário"),
            "T": ("available", candidate.temporal_score, "proximidade da causa")
            if candidate.temporal_score is not None
            else ("not_applicable", None, "família sem evento causal identificável"),
            "C": ("available", corroboration, "fontes independentes relacionadas")
            if corroboration is not None
            else ("unavailable", None, "nenhuma fonte independente disponível"),
            "E": (
                "available",
                candidate.specificity,
                "especificidade semântica do escopo",
            ),
            "I": ("available", _impact(subject), "volume afetado")
            if subject and _impact(subject) is not None
            else ("unavailable", None, "volume afetado indisponível"),
            "Q": ("available", source_q, "qualidade da fonte subject")
            if source_q is not None
            else ("unavailable", None, "canário indisponível"),
        }
        score, coverage, confidence, features = score_features(
            values, contradiction=contradiction
        )
        if contradiction >= 0.80:
            status = "discarded"
        elif candidate.required_missing:
            status = "insufficient_evidence"
        elif score >= 40 and coverage >= 0.50 and generated < max_generated:
            status = "generated"
            generated += 1
        else:
            status = "discarded"
            if score >= 40 and coverage >= 0.50:
                truncated += 1

        evidence: list[Evidence] = []
        if anomaly and subject:
            evidence.append(
                Evidence(
                    "subject",
                    "favorable",
                    "anomalia que iniciou a avaliação",
                    subject,
                    anomaly.observed,
                    anomaly.expected,
                    anomaly.strength,
                    source_q,
                )
            )
        evidence.extend(
            Evidence(
                "supporting",
                "favorable",
                "fato temporal e semanticamente relacionado",
                fact,
                fact.value,
                None,
                0.7,
                _source_quality(fact.source, quality),
            )
            for fact in candidate.supporting
        )
        evidence.extend(candidate.contrary)
        evidence.extend(
            Evidence("required", "missing", missing)
            for missing in candidate.required_missing
        )

        effect_start = (
            subject.event_start
            if subject
            else (
                quality[candidate.scope["source"]].last_observation_at
                or dt.datetime.fromisoformat(
                    quality[candidate.scope["source"]].details["evaluated_at"]
                )
            )
        )
        effect_end = subject.event_end or effect_start if subject else effect_start
        identity = {
            "family": candidate.family,
            "scope": candidate.scope,
            "period": effect_start.replace(second=0, microsecond=0).isoformat(),
        }
        dedup = canonical_hash(
            {
                **identity,
                "facts": sorted(
                    f"{e.fact.fact_key}:{e.fact.version_lsn}"
                    for e in evidence
                    if e.fact is not None
                ),
            }
        )
        supporting_indexes = sorted(
            index
            for index, item in enumerate(anomalies)
            if item.fact.fact_key in {fact.fact_key for fact in candidate.supporting}
            and index != candidate.anomaly_index
        )
        anomaly_indexes = (
            () if candidate.anomaly_index is None else (candidate.anomaly_index,)
        ) + tuple(supporting_indexes)
        lineage = canonical_hash(identity)
        results.append(
            Hypothesis(
                family=candidate.family,
                kind=candidate.kind,
                title=candidate.title,
                summary=candidate.summary,
                scope=candidate.scope,
                effect_start=effect_start,
                effect_end=effect_end,
                score=score,
                coverage=coverage,
                confidence=confidence,
                evaluation_status=status,
                contradiction_strength=contradiction,
                dedup_key=dedup,
                lineage_key=lineage,
                features=features,
                evidence=tuple(evidence),
                anomaly_indexes=anomaly_indexes,
            )
        )

    # `dedup_key` identifica o MESMO candidato dentro do run, e a tabela tem
    # UNIQUE (run_id, dedup_key). Duas fontes independentes que se corroboram
    # (prometheus e apollo no mesmo servico, hora e conjunto de fatos) geram
    # candidatos simetricos: o subject de um e o supporting do outro, e a chave
    # sai identica nos dois. Sem colapsar aqui, o commit inteiro morre com
    # violacao de unicidade -- o que acontecia em qualquer run com duas fontes
    # internas concordando. `results` ja esta na ordem deterministica de
    # `selected`, entao ficar com a primeira ocorrencia e estavel por
    # construcao: a mais forte por (forca, impacto, familia, hash canonico).
    vistos: set[str] = set()
    unicos: list[Hypothesis] = []
    for item in results:
        if item.dedup_key in vistos:
            continue
        vistos.add(item.dedup_key)
        unicos.append(item)

    return tuple(unicos), len(ordered), len(selected), truncated
