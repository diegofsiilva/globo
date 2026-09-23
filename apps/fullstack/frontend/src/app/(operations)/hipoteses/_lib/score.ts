import type { HypothesisFactor } from "./types";

/** Retorna o quanto um fator sustenta a hipótese, independente do seu peso.
 *
 * É o `value` que o motor calcula por fator (0–1, ver `values` em
 * processing/src/argus_processing/rules.py). A versão anterior derivava isso
 * de `contribution / (weight * 100)`, o que só valia enquanto a contribuição
 * vinha em pontos absolutos do mock -- com o score real, normalizado sobre os
 * pesos aplicáveis, a conta estourava 1 e toda barra ficava cheia.
 */
export function factorStrength(factor: HypothesisFactor): number {
  if (factor.value == null) return 0;
  return Math.min(1, Math.max(0, factor.value));
}
