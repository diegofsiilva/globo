/** Adapters HTTP da tela Recorte: heatmap (crosstab) e drill-down de sessão. */

import { QuerySourceError } from "@/lib/operational-state";
import type { ApiEvent } from "@/lib/events/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

if (!API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL não definida. Rode `make frontend-build` ou exporte a " +
      "variável antes de `next build`.",
  );
}

export type CrosstabCell = { x: string; y: string; count: number };

export type CrosstabResponse = {
  dimension_x: string;
  dimension_y: string;
  cells: CrosstabCell[];
};

export type SessionTimelineResponse = {
  session_id: string;
  events: ApiEvent[];
  summary: {
    event_count: number;
    by_event_name: Record<string, number>;
    error_count: number;
    started_at: string;
    ended_at: string;
    device?: { manufacturer?: string | null; model?: string | null; os?: string | null };
    app?: { target?: string | null; version?: string | null };
  };
  next_cursor: string | null;
};

async function requestJson<T>(url: string, signal: AbortSignal | undefined, ref: string): Promise<T> {
  let response: Response;

  try {
    response = await fetch(url, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new QuerySourceError(
      "A conexão com a API de leitura está indisponível. Verifique a rede e tente novamente.",
      "offline",
      `${ref}-OFFLINE`,
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A consulta excedeu o tempo limite."
        : `A API respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `${ref}-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new QuerySourceError(
      "A API respondeu em um formato que a interface não reconhece.",
      "invalid-response",
      `${ref}-INVALID-JSON`,
      false,
    );
  }
}

export type CrosstabFilters = {
  dimensionX: string;
  dimensionY: string;
  eventName?: string;
  from?: string;
  to?: string;
  limit?: number;
};

/** Cruzamento de duas dimensões -- é CONTAGEM, não taxa (ver recorte-content.tsx). */
export function fetchCrosstab(
  filters: CrosstabFilters,
  signal?: AbortSignal,
): Promise<CrosstabResponse> {
  const params = new URLSearchParams({
    dimension_x: filters.dimensionX,
    dimension_y: filters.dimensionY,
    limit: String(filters.limit ?? 100),
  });
  if (filters.eventName) params.set("event_name", filters.eventName);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);

  return requestJson(`${API_URL}/api/v1/metrics/crosstab?${params}`, signal, "ARG-CROSSTAB");
}

/** Linha do tempo completa de uma sessão, para o drill-down do sheet. */
export function fetchSessionTimeline(
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionTimelineResponse> {
  return requestJson(
    `${API_URL}/api/v1/sessions/${encodeURIComponent(sessionId)}?limit=200`,
    signal,
    "ARG-SESSION",
  );
}
