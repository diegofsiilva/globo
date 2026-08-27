/** Adapter HTTP da tela Comparar: changes, referências e série temporal. */

import { QuerySourceError } from "@/lib/operational-state";
import type {
  ChangesResponse,
  LastLivePeakResponse,
  StableWindowResponse,
  TimeseriesResponse,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

if (!API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL não definida. Rode `make frontend-build` ou exporte a " +
      "variável antes de `next build`.",
  );
}

/** GET genérico com o mesmo tratamento de erro tipado do resto do projeto. */
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const endpoint = `${API_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(endpoint, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new QuerySourceError(
      "A conexão com a API de leitura está indisponível. Verifique a rede e tente novamente.",
      "offline",
      "ARG-CMP-OFFLINE",
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A consulta excedeu o tempo limite."
        : `A API respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `ARG-CMP-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new QuerySourceError(
      "A API respondeu em um formato que a interface não reconhece.",
      "invalid-response",
      "ARG-CMP-INVALID-JSON",
      false,
    );
  }
}

export function fetchChanges(
  from: string,
  to: string,
  signal?: AbortSignal,
): Promise<ChangesResponse> {
  const params = new URLSearchParams({ from, to });
  return getJson(`/api/v1/changes?${params}`, signal);
}

export function fetchStableWindow(
  durationMinutes: number,
  signal?: AbortSignal,
): Promise<StableWindowResponse> {
  const params = new URLSearchParams({ duration_minutes: String(durationMinutes) });
  return getJson(`/api/v1/references/stable-window?${params}`, signal);
}

export function fetchLastLivePeak(signal?: AbortSignal): Promise<LastLivePeakResponse> {
  return getJson(`/api/v1/references/last-live-peak`, signal);
}

export function fetchTimeseries(
  filters: { from: string; to: string; interval: number; compare?: boolean },
  signal?: AbortSignal,
): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({
    from: filters.from,
    to: filters.to,
    interval: String(filters.interval),
  });
  if (filters.compare) params.set("compare", "true");
  return getJson(`/api/v1/metrics/timeseries?${params}`, signal);
}
