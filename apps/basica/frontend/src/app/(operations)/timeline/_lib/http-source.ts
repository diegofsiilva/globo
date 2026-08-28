/** Adapter HTTP de `GET /api/v1/timeline`. Mesmo padrão de erro do adapter de hipóteses. */

import { QuerySourceError } from "@/lib/operational-state";
import type { TimelineApiResponse, TimelineQuery } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

/** Busca as seis raias de fonte para a janela pedida (ou a janela padrão do servidor). */
export async function fetchTimeline(
  query: TimelineQuery = {},
  signal?: AbortSignal,
): Promise<TimelineApiResponse> {
  if (!API_URL) {
    throw new Error(
      "NEXT_PUBLIC_API_URL não definida. Rode `make frontend-build` ou exporte a " +
        "variável antes de `next build`.",
    );
  }

  const params = new URLSearchParams();
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);

  const endpoint = `${API_URL}/api/v1/timeline?${params}`;
  let response: Response;

  try {
    response = await fetch(endpoint, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new QuerySourceError(
      "A conexão com a API de leitura está indisponível. Verifique a rede e tente novamente.",
      "offline",
      "ARG-TL-OFFLINE",
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A consulta da timeline excedeu o tempo limite."
        : `A API respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `ARG-TL-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  try {
    return (await response.json()) as TimelineApiResponse;
  } catch {
    throw new QuerySourceError(
      "A API respondeu em um formato que a interface não reconhece.",
      "invalid-response",
      "ARG-TL-INVALID-JSON",
      false,
    );
  }
}
