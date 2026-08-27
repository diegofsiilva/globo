/** Adapter HTTP da tela Explorar: breakdown, timeseries e facets. */

import { QuerySourceError } from "@/lib/operational-state";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

if (!API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL não definida. Rode `make frontend-build` ou exporte a " +
      "variável antes de `next build`.",
  );
}

export type BreakdownGroup = {
  key: string;
  count: number;
  share: number;
  average_duration_ms: number | null;
};

export type BreakdownResponse = {
  dimension: string;
  total: number;
  groups: BreakdownGroup[];
};

export type TimeseriesBucket = {
  bucket: string;
  count: number;
  by_event_name: Record<string, number>;
};

export type TimeseriesResponse = {
  interval_minutes: number;
  total: number;
  buckets: TimeseriesBucket[];
};

export type FacetsResponse = { facets: Record<string, string[]> };

/** Escopo de filtros cumulativos aceito por `filters_from_query` no backend. */
export type EventScope = Partial<{
  event_name: string;
  device_os: string;
  device_manufacturer: string;
  app_version: string;
  uf: string;
  isp: string;
}>;

async function getJson<T>(
  path: string,
  params: URLSearchParams,
  signal: AbortSignal | undefined,
  reference: string,
): Promise<T> {
  const endpoint = `${API_URL.replace(/\/$/, "")}${path}?${params}`;
  let response: Response;

  try {
    response = await fetch(endpoint, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new QuerySourceError(
      "A conexão com a API de leitura está indisponível. Verifique a rede e tente novamente.",
      "offline",
      `${reference}-OFFLINE`,
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A API excedeu o tempo limite da consulta."
        : `A API respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `${reference}-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new QuerySourceError(
      "A API respondeu em um formato que a interface não reconhece.",
      "invalid-response",
      `${reference}-INVALID-JSON`,
      false,
    );
  }
}

function withScope(params: URLSearchParams, scope: EventScope) {
  for (const [key, value] of Object.entries(scope)) {
    if (value) params.set(key, value);
  }
  return params;
}

export function fetchBreakdown(
  dimension: string,
  window: { from: string; to: string },
  scope: EventScope,
  signal?: AbortSignal,
): Promise<BreakdownResponse> {
  const params = withScope(
    new URLSearchParams({ dimension, from: window.from, to: window.to, limit: "100" }),
    scope,
  );
  return getJson<BreakdownResponse>("/api/v1/metrics/breakdown", params, signal, "ARG-EXP-BREAKDOWN");
}

export function fetchTimeseries(
  window: { from: string; to: string },
  intervalMinutes: number,
  scope: EventScope,
  signal?: AbortSignal,
): Promise<TimeseriesResponse> {
  const params = withScope(
    new URLSearchParams({ from: window.from, to: window.to, interval: String(intervalMinutes) }),
    scope,
  );
  return getJson<TimeseriesResponse>("/api/v1/metrics/timeseries", params, signal, "ARG-EXP-TIMESERIES");
}

export function fetchFacets(fields: string[], signal?: AbortSignal): Promise<FacetsResponse> {
  const params = new URLSearchParams();
  for (const field of fields) params.append("field", field);
  return getJson<FacetsResponse>("/api/v1/facets", params, signal, "ARG-EXP-FACETS");
}
