/** Adapter HTTP do relatório de hipóteses de causa provável. */

import { apiFetch } from "@/lib/api/client";
import { QuerySourceError } from "@/lib/operational-state";
import type { ApiHypothesesPage } from "./api-types";
import { toHypothesesReport } from "./mapper";
import type { HypothesesSource } from "./types";

/**
 * Cria um adapter HTTP do relatório de hipóteses.
 *
 * @returns Função que consulta `/api/v1/hypotheses` e devolve o relatório já
 *   no formato da tela.
 */
export function createHttpHypothesesSource(): HypothesesSource {
  return async (filters = {}, signal) => {
    const params = new URLSearchParams();

    if (filters.from) params.set("from", filters.from);
    if (filters.to) params.set("to", filters.to);
    if (filters.cursor) params.set("cursor", filters.cursor);
    params.set("limit", "200");
    for (const [key, value] of Object.entries(filters.scope ?? {})) {
      params.set(key, value);
    }

    // A API devolve `{count, items}` -- NAO o relatório da tela. Antes daqui
    // o adapter fazia `return response.json()` cru, e a tela quebrava em
    // `report.summary.trafficShare` (undefined) assim que saía do mock.
    const page = await apiFetch<ApiHypothesesPage>(`/api/v1/hypotheses?${params}`, {
      tag: "HYP",
      signal,
    });

    if (!page || !Array.isArray(page.items)) {
      throw new QuerySourceError(
        "O motor de hipóteses respondeu sem a lista de hipóteses.",
        "invalid-response",
        "ARG-HYP-INVALID-SHAPE",
        false,
      );
    }

    return toHypothesesReport(page, filters);
  };
}
