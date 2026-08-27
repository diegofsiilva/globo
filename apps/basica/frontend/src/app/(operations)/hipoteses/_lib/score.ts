import type { HypothesisFactor } from "./types";

/** Retorna o quanto um fator sustenta a hipótese, independente do seu peso. */
export function factorStrength(factor: HypothesisFactor): number {
  if (factor.weight <= 0) return 0;
  return Math.min(1, factor.contribution / (factor.weight * 100));
}
