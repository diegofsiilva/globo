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
  scope?: Record<string, string>;
};

/** Interface comum aos adapters HTTP e mock do relatório de hipóteses. */
export type HypothesesSource = (
  filters?: HypothesesFilters,
  signal?: AbortSignal,
) => Promise<HypothesesReport>;
