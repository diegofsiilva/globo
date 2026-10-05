/** Fator ponderado que compõe o score de uma hipótese. */
export type HypothesisFactor = {
  id: string;
  label: string;
  weight: number;
  /** Pontos do score que este fator ocupa (a faixa soma o score). */
  contribution: number;
  rationale: string;
  /** Quanto o fator sustenta a hipótese, 0–1, independente do peso. */
  value: number | null;
  applicability: "available" | "unavailable" | "not_applicable";
};

/** Fonte de evidência consultada para montar uma hipótese. */
export type EvidenceSource = {
  source: string;
  detail: string;
  /**
   * De que lado da hipótese a evidência está. Uma hipótese que só mostra o que
   * a sustenta é um argumento, não um diagnóstico.
   */
  polarity?: "a favor" | "contra" | "ausente";
  /** Instante do fato, já formatado. */
  at?: string;
};

/** Hipótese de causa provável, ranqueada por score. */
export type Hypothesis = {
  id: string;
  category: string;
  title: string;
  score: number;
  confidence: "alta" | "média" | "baixa";
  factors: HypothesisFactor[];
  evidence: EvidenceSource[];
  timelineAnchor: string;
  segment: string;
  /** Frase do motor explicando a hipótese em linguagem corrente. */
  summary?: string;
  /** Quando o efeito foi observado, já formatado (`dd/mm hh:mm`). */
  effect?: string;
  /** Natureza da hipótese: operacional, contexto ou qualidade de dado. */
  kind?: string;
  /** Fração (0–1) da evidência exigida pela família que estava disponível. */
  coverage?: number | null;
  /** Situação da revisão humana. */
  reviewStatus?: "não revisada" | "confirmada" | "parcialmente confirmada" | "rejeitada";
};

/** Hipótese avaliada e rejeitada, com o motivo do descarte. */
export type DiscardedHypothesis = {
  id: string;
  score: number;
  title: string;
  reason: string;
};

/** Filtro aplicado ao recorte, exibido na barra de escopo. */
export type ScopeChip = {
  id: string;
  label: string;
  value: string;
};

/** Relatório completo devolvido pelo motor de hipóteses. */
export type HypothesesReport = {
  nextCursor?: string | null;
  window: { from: string; to: string; label: string };
  generated: number;
  discarded: number;
  scope: ScopeChip[];
  summary: { hypotheses: number; families: number; sources: number };
  hypotheses: Hypothesis[];
  discardedHypotheses: DiscardedHypothesis[];
};

/** Filtros aceitos pelo relatório, espelhando a query string da API. */
export type HypothesesFilters = {
  from?: string;
  to?: string;
  cursor?: string;
  scope?: Record<string, string>;
};

/** Interface comum aos adapters HTTP e mock do relatório de hipóteses. */
export type HypothesesSource = (
  filters?: HypothesesFilters,
  signal?: AbortSignal,
) => Promise<HypothesesReport>;
