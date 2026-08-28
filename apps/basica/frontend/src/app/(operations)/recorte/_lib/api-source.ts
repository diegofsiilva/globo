/** Adapters HTTP da tela Recorte: heatmap (crosstab) e drill-down de sessão.
 *
 * O heatmap passou a ler `/api/v1/series/crosstab`, sobre
 * `gold.v_feature_bucket`. O drill-down por sessão continua em
 * `/api/v1/sessions/<id>` e NÃO tem lastro neste dump: não existe evento por
 * sessão individual no dataset do Argus, só telemetria agregada por hora. */

import { getJson, withScope, type EventScope } from "@/lib/events/query";
import type { ApiEvent } from "@/lib/events/api";

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

export type CrosstabFilters = {
  dimensionX: string;
  dimensionY: string;
  metric?: string;
  from?: string;
  to?: string;
  limit?: number;
  /** Recorte declarado na barra de escopo; vazio significa "todo o tráfego". */
  scope?: EventScope;
};

/** Cruzamento de duas dimensões da série agregada.
 *
 * O valor da célula é a agregação da métrica pedida -- soma para contagem,
 * média para taxa (ver `_agregacao` em infrastructure/gold.py). */
export async function fetchCrosstab(
  filters: CrosstabFilters,
  signal?: AbortSignal,
): Promise<CrosstabResponse> {
  const params = new URLSearchParams({
    dimension_x: filters.dimensionX,
    dimension_y: filters.dimensionY,
    limit: String(filters.limit ?? 400),
  });
  if (filters.metric) params.set("metric", filters.metric);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  withScope(params, filters.scope ?? {});

  const bruto = await getJson<{
    dimension_x: string;
    dimension_y: string;
    cells: { x: string; y: string; value: number | null; points: number }[];
  }>("/api/v1/series/crosstab", params, signal, "ARG-CROSSTAB");

  return {
    dimension_x: bruto.dimension_x,
    dimension_y: bruto.dimension_y,
    cells: bruto.cells.map((celula) => ({
      x: celula.x,
      y: celula.y,
      count: celula.value ?? 0,
    })),
  };
}

/** Linha do tempo completa de uma sessão, para o drill-down do sheet. */
export function fetchSessionTimeline(
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionTimelineResponse> {
  return getJson(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    new URLSearchParams({ limit: "200" }),
    signal,
    "ARG-SESSION",
  );
}
