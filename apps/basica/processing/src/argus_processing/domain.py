"""Contratos imutaveis do detector e do motor de hipoteses."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

Availability = Literal["available", "unavailable", "not_applicable"]


@dataclass(frozen=True, slots=True)
class Fact:
    """Uma observacao de fonte, ja normalizada, no grain em que a analise trabalha.

    Sai de `bronze.change_log` e nao da tabela corrente: e o que conserva duas
    mudancas da mesma PK que cheguem entre dois ciclos do ETL (AGENTS.md, regra
    2). `version_lsn` e a ordem dessas versoes.

    `available_at` e o instante em que a informacao ficaria disponivel na vida
    real, contando a latencia da fonte -- 28 h na NPAW, 1 min no Prometheus.
    Nenhuma regra pode olhar um fato cujo `available_at` esteja a frente de
    `sim.now()`, sob pena de explicar um incidente com dado que ainda nao teria
    chegado.
    """

    fact_key: str
    version_lsn: int
    role: str
    kind: str
    event_start: dt.datetime
    event_end: dt.datetime | None
    available_at: dt.datetime
    source: str
    entity: str
    metric: str
    dimension_type: str | None
    dimension_value: str | None
    value: float | None
    sample_size: int | None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Baseline:
    """Media e variancia acumuladas de uma serie, no formato de Welford.

    Mutavel (sem `frozen`) de proposito: o detector atualiza o baseline a cada
    bucket dentro do ciclo, e criar um objeto novo por bucket custaria uma
    alocacao por ponto de serie.

    `n < 3` significa historico insuficiente -- o z-score correspondente sai
    `None` em vez de um numero calculado sobre duas amostras.
    """

    mean: float | None = None
    variance: float | None = None
    n: int = 0
    last_event_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class Anomaly:
    """Um fato que se afastou do baseline o suficiente para virar sinal.

    `strength` e a magnitude ja normalizada para a faixa usada pelo score;
    `z` e o desvio em unidades de desvio-padrao, preservado para que a
    evidencia mostrada ao operador possa citar o numero original.

    `persisted_id` so e preenchido depois da gravacao -- antes disso a anomalia
    existe apenas dentro do ciclo.
    """

    fact: Fact
    observed: float
    expected: float
    direction: str
    deviation: float
    z: float
    strength: float
    baseline_snapshot: dict[str, Any]
    persisted_id: int | None = None


@dataclass(frozen=True, slots=True)
class SourceQuality:
    """Veredito do canario sobre uma fonte, num ciclo.

    Existe porque uma fonte silenciosa e indistinguivel de uma fonte saudavel
    sem incidente: as duas produzem zero anomalia. Sem esta medida, o motor
    concluiria "nada de errado" justamente quando parou de enxergar.

    As quatro dimensoes (`freshness`, `completeness`, `validity`,
    `consistency`) sao ponderadas em `quality_score`, e uma hipotese apoiada em
    fonte de qualidade baixa tem o score reduzido em vez de ser descartada --
    descartar esconderia o problema.
    """

    source: str
    expected_cadence_seconds: int
    last_observation_at: dt.datetime | None
    freshness: float | None
    completeness: float | None
    validity: float | None
    consistency: float | None
    quality_score: float | None
    status: str
    expected_buckets: int
    observed_buckets: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Feature:
    """Um componente do score de uma hipotese, com a sua explicacao.

    `applicability` distingue tres situacoes que um numero sozinho confunde:
    a feature foi calculada (`available`), a fonte necessaria nao respondeu
    (`unavailable`) ou a feature nao faz sentido para esta familia
    (`not_applicable`). Sem essa distincao, ausencia de dado viraria zero, e
    zero puxaria o score para baixo como se fosse evidencia contraria.
    """

    name: str
    applicability: Availability
    value: float | None
    weight: float
    contribution: float | None
    explanation: str


@dataclass(frozen=True, slots=True)
class Evidence:
    """Um fato citado a favor ou contra uma hipotese.

    `polarity` e o que permite mostrar ao operador tambem o que NAO fecha com a
    explicacao. Uma hipotese que so exibe evidencia favoravel e um argumento,
    nao um diagnostico -- e o operador nao teria como discordar dela.
    """

    role: str
    polarity: str
    explanation: str
    fact: Fact | None = None
    observed: float | None = None
    expected: float | None = None
    strength: float | None = None
    quality: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """Uma explicacao candidata e auditavel, para revisao humana.

    Nao e causa-raiz confirmada (AGENTS.md). `evaluation_status` e
    `contradiction_strength` carregam o quanto a propria evidencia contradiz a
    explicacao, e `confidence` traduz o score numa faixa que o operador le sem
    saber o que e o score.

    `dedup_key` colapsa a mesma hipotese reemitida em ciclos seguidos;
    `lineage_key` a liga as suas versoes anteriores, para que a tela mostre
    "isto continua acontecendo" em vez de repetir o mesmo item.
    """

    family: str
    kind: str
    title: str
    summary: str
    scope: dict[str, Any]
    effect_start: dt.datetime
    effect_end: dt.datetime
    score: float
    coverage: float
    confidence: str
    evaluation_status: str
    contradiction_strength: float
    dedup_key: str
    lineage_key: str
    features: tuple[Feature, ...]
    evidence: tuple[Evidence, ...]
    anomaly_indexes: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Tudo que um ciclo de analise produziu, para gravacao numa transacao.

    Os tres contadores de candidato nao sao estatistica de curiosidade: sao o
    que distingue "nao ha hipotese" de "havia candidatos demais e o ciclo parou
    no teto". Sem eles, um ciclo truncado se apresentaria como um ciclo limpo.
    """

    anomalies: tuple[Anomaly, ...]
    finding_anomalies: tuple[Anomaly, ...]
    baseline_updates: dict[tuple[str, str, str, int], Baseline]
    quality: tuple[SourceQuality, ...]
    hypotheses: tuple[Hypothesis, ...]
    candidates_prefiltered: int
    candidates_evaluated: int
    candidates_truncated: int
