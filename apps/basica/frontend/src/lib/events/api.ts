/** Cliente tipado da API de leitura de eventos. */

import { apiFetch } from "@/lib/api/client";
import { withScope, type EventScope } from "./query";

export type ApiEvent = {
  action: string | null;
  app_bucket: string | null;
  app_env: string | null;
  app_target: string | null;
  app_version: string | null;
  attributes: Record<string, unknown>;
  clock_skew: boolean;
  device_id: string;
  device_manufacturer: string | null;
  device_model: string | null;
  device_model_year: number | string | null;
  device_os: string | null;
  device_os_version: string | null;
  duration_ms: number | null;
  event_id: string;
  event_name: string;
  ingested_at: string | null;
  occurred_at: string;
  route_path: string | null;
  session_id: string;
};

export type EventsResponse = {
  items: ApiEvent[];
  next_cursor: string | null;
  query: { strategy: string; scanned: number; returned: number; queries: number };
};

export type EventQuery = {
  eventName?: string;
  platform?: string;
  manufacturer?: string;
  from?: string;
  to?: string;
  /** Recorte declarado na barra de escopo; vazio significa "todo o tráfego". */
  scope?: EventScope;
};

/**
 * Consulta eventos aplicando somente os filtros preenchidos.
 *
 * @param filters Filtros da tela; chaves vazias são omitidas.
 * @param signal Aborta quando a tela desmonta ou o filtro muda.
 * @returns Página keyset de eventos com o bloco `query` de custo.
 */
export async function fetchEvents(
  filters: EventQuery,
  signal?: AbortSignal,
): Promise<EventsResponse> {
  const params = new URLSearchParams({ limit: "100" });

  if (filters.eventName) params.set("event_name", filters.eventName);
  if (filters.platform) params.set("device_os", filters.platform);
  if (filters.manufacturer) params.set("device_manufacturer", filters.manufacturer);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  withScope(params, filters.scope ?? {});

  return apiFetch<EventsResponse>(`/api/v1/events?${params}`, { tag: "EVENTS", signal });
}
