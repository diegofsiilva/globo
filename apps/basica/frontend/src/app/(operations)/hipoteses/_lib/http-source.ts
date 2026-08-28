/** Adapter HTTP do relatório de hipóteses de causa provável. */

import type { HypothesesSource } from "./types";
import type { ApiHypothesesPage } from "./api-types";
import { toHypothesesReport } from "./mapper";
import { QuerySourceError } from "@/lib/operational-state";

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

    const endpoint = `${normalizedUrl}/api/v1/hypotheses?${params}`;
    let response: Response;

    try {
      response = await fetch(endpoint, { signal });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new QuerySourceError(
        "A conexão com o motor de hipóteses está indisponível. Verifique a rede e tente novamente.",
        "offline",
        "ARG-HYP-OFFLINE",
      );
    }

    if (!response.ok) {
      const timeout = response.status === 408 || response.status === 504;
      throw new QuerySourceError(
        timeout
          ? "O motor de hipóteses excedeu o tempo limite da consulta."
          : `O motor de hipóteses respondeu com status ${response.status}.`,
        timeout ? "timeout" : "server",
        `ARG-HYP-HTTP-${response.status}`,
        response.status >= 500 || timeout,
      );
    }

    // A API devolve `{count, items}` -- NAO o relatório da tela. Antes daqui
    // o adapter fazia `return response.json()` cru, e a tela quebrava em
    // `report.summary.trafficShare` (undefined) assim que saía do mock.
    let page: ApiHypothesesPage;
    try {
      page = (await response.json()) as ApiHypothesesPage;
    } catch {
      throw new QuerySourceError(
        "O motor de hipóteses respondeu em um formato que a interface não reconhece.",
        "invalid-response",
        "ARG-HYP-INVALID-JSON",
        false,
      );
    }

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
