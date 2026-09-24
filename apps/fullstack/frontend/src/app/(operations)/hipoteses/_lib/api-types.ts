/** Formato bruto devolvido por `GET /api/v1/hypotheses`.
 *
 * Deliberadamente separado de `types.ts`: aquele descreve o que a TELA
 * consome, este descreve o que a API ENTREGA. Foi a ausência dessa separação
 * que deixou o adapter HTTP devolver `response.json()` cru tipado como
 * `HypothesesReport` -- o build passava e a tela quebrava em runtime.
 */

/**
 * Uma componente do score, com a sua explicação.
 *
 * `applicability` distingue três situações que um número sozinho confunde: a
 * feature foi calculada, a fonte necessária não respondeu (`unavailable`) ou a
 * feature não se aplica a esta família (`not_applicable`). Sem essa distinção,
 * ausência de dado viraria zero, e zero puxaria o score para baixo como se fosse
 * evidência contrária.
 */
export type ApiFeature = {
  feature: string;
  applicability: "available" | "unavailable" | "not_applicable";
  value: number | null;
  weight: number;
  contribution: number | null;
  explanation: string;
};

/**
 * Um fato citado a favor ou contra a hipótese.
 *
 * `polarity` é o que permite mostrar ao operador também o que NÃO fecha com a
 * explicação. Uma hipótese que só exibe evidência favorável é um argumento, não
 * um diagnóstico — e o operador não teria como discordar dela.
 */
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

/**
 * Uma hipótese gerada e visível.
 *
 * É uma explicação candidata e auditável, para revisão humana — não uma
 * causa-raiz confirmada. `contradiction_strength` e `evaluation_status`
 * carregam o quanto a própria evidência contradiz a explicação, e `confidence`
 * traduz o score numa faixa que o operador lê sem saber o que é o score.
 */
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

/**
 * Uma página de hipóteses.
 *
 * `next_cursor` é opaco e keyset. Um cursor corrompido devolve 422, nunca a
 * primeira página em silêncio — que faria o cliente paginar em círculo sem
 * perceber.
 */
export type ApiHypothesesPage = {
  count: number;
  items: ApiHypothesis[];
  next_cursor: string | null;
};
