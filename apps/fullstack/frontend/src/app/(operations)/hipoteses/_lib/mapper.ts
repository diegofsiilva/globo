/** Tradução do payload da API para a forma que a tela de Hipóteses consome. */

import type { ApiEvidence, ApiFeature, ApiHypothesis, ApiHypothesesPage } from "./api-types";
import type {
  EvidenceSource,
  Hypothesis,
  HypothesesReport,
  HypothesisFactor,
} from "./types";

/** Rótulo pt-BR de cada família do motor (FAMILIES em hypotheses_http.py). */
const familyLabels: Record<string, string> = {
  deploy_regression: "regressão de deploy",
  backend_internal: "falha interna de backend",
  playback_authorization: "autorização de playback",
  cdn_degradation: "degradação de CDN",
  origin_encoding: "origem ou encoding",
  regional_or_isp: "região ou provedor",
  waf_block: "bloqueio de WAF",
  player_or_device: "player ou dispositivo",
  qoe_without_error: "QoE sem erro",
  expected_live_peak: "pico de audiência esperado",
  source_data_delay: "atraso na fonte de dados",
};

/** Nome curto de cada fator do score (values em processing/rules.py). */
const featureLabels: Record<string, string> = {
  A: "Desvio",
  C: "Corroboração",
  E: "Especificidade",
  I: "Impacto",
  Q: "Qualidade da fonte",
  T: "Proximidade temporal",
  X: "Contradição",
};

const confidenceLabels: Record<string, Hypothesis["confidence"]> = {
  high: "alta",
  medium: "média",
  low: "baixa",
};

/** Rótulo pt-BR da natureza da hipótese (`kind` em 021_hypothesis_engine.sql). */
const kindLabels: Record<string, string> = {
  operational: "operacional",
  context: "contexto",
  data_quality: "qualidade de dado",
};

/** Rótulo pt-BR da revisão humana (`review_status` em 021_hypothesis_engine.sql). */
const reviewLabels: Record<string, NonNullable<Hypothesis["reviewStatus"]>> = {
  unreviewed: "não revisada",
  confirmed: "confirmada",
  partially_confirmed: "parcialmente confirmada",
  rejected: "rejeitada",
};

const polarityLabels: Record<string, NonNullable<EvidenceSource["polarity"]>> = {
  favorable: "a favor",
  contrary: "contra",
  missing: "ausente",
};

/**
 * Filtros que `GET /api/v1/hypotheses` aceita, com o rótulo exibido e o valor
 * enviado. A rota valida cada um contra um conjunto fechado e responde 422 a
 * valor desconhecido, então as opções saem daqui e não de texto livre.
 */
export const HYPOTHESIS_FILTERS = [
  { key: "family", label: "família", options: invert(familyLabels) },
  { key: "kind", label: "tipo", options: invert(kindLabels) },
  { key: "confidence", label: "confiança", options: invert(confidenceLabels) },
  { key: "review_status", label: "revisão", options: invert(reviewLabels) },
] as const;

/** Chaves de filtro aceitas pela tela. */
export type HypothesisFilterKey = (typeof HYPOTHESIS_FILTERS)[number]["key"];

function invert(labels: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(labels).map(([value, label]) => [label, value]));
}

/** Converte a página da API no relatório da tela. */
export function toHypothesesReport(
  page: ApiHypothesesPage,
  window: { from?: string; to?: string },
): HypothesesReport {
  const items = page.items ?? [];
  const hypotheses = items.map(toHypothesis);

  // `gold.v_hypothesis` filtra `evaluation_status = 'generated'`
  // (022_hypothesis_views.sql), então a API NUNCA devolve descartada. A lista
  // fica vazia de propósito -- inventar uma aqui seria mentir sobre o que o
  // motor rejeitou. O componente `DiscardedList` já não renderiza nada quando
  // recebe lista vazia.
  const families = new Set(items.map((item) => item.family));
  const sources = new Set(items.flatMap((item) => (item.evidence ?? []).map((e) => e.source)));

  return {
    nextCursor: page.next_cursor,
    window: {
      from: window.from ?? items[0]?.effect_start ?? "",
      to: window.to ?? items[0]?.effect_end ?? "",
      label: windowLabel(items),
    },
    generated: page.count ?? hypotheses.length,
    discarded: 0,
    scope: [],
    summary: {
      hypotheses: hypotheses.length,
      families: families.size,
      sources: sources.size,
    },
    hypotheses,
    discardedHypotheses: [],
  };
}

function toHypothesis(item: ApiHypothesis): Hypothesis {
  return {
    id: String(item.hypothesis_id),
    category: familyLabels[item.family] ?? item.family,
    title: item.title,
    score: Math.round(item.score),
    confidence: confidenceLabels[item.confidence] ?? "baixa",
    factors: toFactors(item.features ?? [], item.score),
    evidence: (item.evidence ?? []).map(toEvidence),
    timelineAnchor: item.effect_start,
    segment: scopeLabel(item.scope),
    summary: item.summary,
    effect: effectLabel(item.effect_start, item.effect_end),
    kind: kindLabels[item.kind] ?? item.kind,
    coverage: item.coverage,
    reviewStatus: reviewLabels[item.review_status] ?? "não revisada",
  };
}

/** Distribui o score entre os fatores aplicáveis.
 *
 * O motor normaliza o score sobre os pesos APLICÁVEIS: no exemplo real, sete
 * fatores com contribuições somando 0,65 produzem score 100, porque `I` e `T`
 * ficaram indisponíveis. Multiplicar a contribuição por 100 desenharia uma
 * faixa de 65 pontos numa hipótese de 100 -- por isso a proporção aqui é
 * sobre o total contribuído, e não sobre 1.
 */
function toFactors(features: ApiFeature[], score: number): HypothesisFactor[] {
  const total = features.reduce((soma, f) => soma + (f.contribution ?? 0), 0);

  return features
    // Fator sem contribuição não ocupa espaço na faixa; ele continua na lista
    // do painel, com a razão do "indisponível" visível (é informação real
    // sobre a limitação do dado, não ruído).
    .filter((f) => f.applicability === "available" || (f.contribution ?? 0) > 0 || f.value !== null)
    .map((f) => ({
      id: f.feature,
      label: featureLabels[f.feature] ?? f.feature,
      weight: f.weight,
      contribution: total > 0 ? ((f.contribution ?? 0) / total) * score : 0,
      rationale: f.explanation,
      value: f.value,
      applicability: f.applicability,
    }));
}

function toEvidence(item: ApiEvidence): EvidenceSource {
  const medida =
    item.observed != null && item.expected != null
      ? `${formatNumber(item.observed)} contra ${formatNumber(item.expected)} esperado`
      : null;
  const partes = [item.metric, item.entity, medida, item.explanation].filter(Boolean);
  const instante = new Date(item.event_at).getTime();
  return {
    source: `${item.source}:${item.evidence_id}`,
    detail: partes.join(" · "),
    polarity: polarityLabels[item.polarity],
    at: Number.isFinite(instante) ? formatMoment(instante) : undefined,
  };
}

/**
 * Quando o efeito foi observado.
 *
 * O dia vai junto: a lista cobre até 24 h do relógio virtual, e duas hipóteses
 * com o mesmo título em dias diferentes ficavam indistinguíveis.
 */
function effectLabel(start: string, end: string): string | undefined {
  const inicio = new Date(start).getTime();
  const fim = new Date(end).getTime();
  if (!Number.isFinite(inicio)) return undefined;
  if (!Number.isFinite(fim) || fim <= inicio) return formatMoment(inicio);
  const mesmoDia = dayFormatter.format(new Date(inicio)) === dayFormatter.format(new Date(fim));
  return `${formatMoment(inicio)} → ${mesmoDia ? formatTime(fim) : formatMoment(fim)}`;
}

function scopeLabel(scope: Record<string, string> | null | undefined): string {
  const entradas = Object.entries(scope ?? {});
  if (entradas.length === 0) return "escopo global";
  return entradas.map(([chave, valor]) => `${chave}=${valor}`).join(" · ");
}

function windowLabel(items: ApiHypothesis[]): string {
  if (items.length === 0) return "sem janela";
  const inicios = items.map((i) => new Date(i.effect_start).getTime()).filter(Number.isFinite);
  const fins = items.map((i) => new Date(i.effect_end).getTime()).filter(Number.isFinite);
  if (inicios.length === 0 || fins.length === 0) return "sem janela";
  return `${formatTime(Math.min(...inicios))} – ${formatTime(Math.max(...fins))}`;
}

const numberFormatter = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const timeFormatter = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

function formatTime(epoch: number): string {
  return timeFormatter.format(new Date(epoch));
}

const dayFormatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });

function formatMoment(epoch: number): string {
  return `${dayFormatter.format(new Date(epoch))} ${formatTime(epoch)}`;
}
