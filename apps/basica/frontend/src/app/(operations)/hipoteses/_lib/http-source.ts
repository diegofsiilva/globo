/** Adapter HTTP do relatório de hipóteses de causa provável. */

import type { HypothesesSource } from "./types";

/** Cria um adapter HTTP preso à URL configurada no build. */
export function createHttpHypothesesSource(apiUrl: string): HypothesesSource {
  const normalizedUrl = apiUrl.replace(/\/$/, "");

  return async (filters = {}, signal) => {
    const params = new URLSearchParams();

    if (filters.from) params.set("from", filters.from);
    if (filters.to) params.set("to", filters.to);
    for (const [key, value] of Object.entries(filters.scope ?? {})) {
      params.set(key, value);
    }

    const response = await fetch(
      `${normalizedUrl}/api/v1/hypotheses?${params}`,
      { signal },
    );

    if (!response.ok) {
      throw new Error(`A API respondeu com status ${response.status}`);
    }

    return response.json();
  };
}
