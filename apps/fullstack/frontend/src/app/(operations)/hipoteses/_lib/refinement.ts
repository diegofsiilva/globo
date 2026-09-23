/** Consulta a explicacao Ollama ancorada em uma hipotese publicada. */

import { apiFetch } from "@/lib/api/client";

/** Uma afirmacao do modelo e as fontes da hipotese que a sustentam. */
export type GroundedStatement = {
  text: string;
  source_ids: string[];
};

/** Resposta refinada, ja validada pelo backend contra as fontes permitidas. */
export type HypothesisRefinement = {
  hypothesis_id: number;
  answerable: boolean;
  answer: string;
  claims: GroundedStatement[];
  limitations: GroundedStatement[];
  sources: Array<{ id: string; value: unknown }>;
  model: string;
  grounding: "hypothesis_only";
};

/** O mock nao inventa uma resposta de LLM; o recurso aparece somente com API real. */
export const hypothesisRefinementEnabled =
  process.env.NEXT_PUBLIC_HYPOTHESES_SOURCE === "api";

/**
 * Solicita uma explicacao concisa sem autorizar fontes externas.
 *
 * @param hypothesisId Hipotese publicada selecionada pelo operador.
 * @returns Texto refinado, afirmacoes e ids das fontes usadas.
 */
export async function refineHypothesis(
  hypothesisId: string,
): Promise<HypothesisRefinement> {
  return apiFetch<HypothesisRefinement>(
    `/api/v1/hypotheses/${encodeURIComponent(hypothesisId)}/refinement`,
    {
      tag: "HYP-REFINE",
      method: "POST",
      body: {
        question: "Explique esta hipótese e as evidências que a sustentam.",
      },
    },
  );
}
