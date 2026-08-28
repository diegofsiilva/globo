/** Formato bruto devolvido por `GET /api/v1/hypotheses`.
 *
 * Deliberadamente separado de `types.ts`: aquele descreve o que a TELA
 * consome, este descreve o que a API ENTREGA. Foi a ausência dessa separação
 * que deixou o adapter HTTP devolver `response.json()` cru tipado como
 * `HypothesesReport` -- o build passava e a tela quebrava em runtime.
 */

export type ApiFeature = {
  feature: string;
  applicability: "available" | "unavailable" | "not_applicable";
  value: number | null;
  weight: number;
  contribution: number | null;
  explanation: string;
};

export type ApiEvidence = {
  evidence_id: number;
  role: string;
  polarity: string;
  explanation: string;
  source: string;
  entity: string;
  metric: string;
  observed: number | null;
  expected: number | null;
  strength: number | null;
  quality: number | null;
  event_at: string;
};

export type ApiHypothesis = {
  hypothesis_id: number;
  family: string;
  kind: string;
  title: string;
  summary: string;
  scope: Record<string, string>;
  effect_start: string;
  effect_end: string;
  score: number;
  coverage: number;
  confidence: "high" | "medium" | "low";
  evaluation_status: string;
  review_status: string;
  contradiction_strength: number;
  sim_now: string;
  // Anexados pela rota de lista (ver `_anexar_composicao` no repositório):
  // sem eles a faixa de contribuição da lista não tem o que desenhar.
  features?: ApiFeature[];
  evidence?: ApiEvidence[];
};

export type ApiHypothesesPage = {
  count: number;
  items: ApiHypothesis[];
  next_cursor: string | null;
};
