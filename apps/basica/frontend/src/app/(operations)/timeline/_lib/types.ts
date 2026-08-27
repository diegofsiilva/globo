/** Formato de `GET /api/v1/timeline` (seis raias de fonte). */

export type SeriesPoint = {
  bucket_ts: string;
  entity: string;
  metric: string;
  value: number;
};

export type DeployPoint = {
  event_id: string;
  kind: string | null;
  target_type: string | null;
  target_value: string | null;
  owner: string | null;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  error: string | null;
};

export type IncidentPoint = {
  window_id: number;
  ts_start: string;
  ts_end: string;
  origem: string;
  ref_id: string;
  verdict: string | null;
  severity: string | null;
  provenance: string | null;
};

/**
 * Tipo da raia (a fonte), não confundir com o `kind` visual de
 * `TimelineRow` em `_mocks/scenario.ts` (esse é o peso/cor de cada barra).
 */
export type LaneType = "series" | "events" | "incidents";

export type TimelineLane =
  | { source: string; label: string; lane_type: "series"; points: SeriesPoint[] }
  | { source: string; label: string; lane_type: "events"; points: DeployPoint[] }
  | { source: string; label: string; lane_type: "incidents"; points: IncidentPoint[] };

export type TimelineApiResponse = {
  window: { from: string; to: string };
  lanes: TimelineLane[];
};

export type TimelineQuery = {
  from?: string;
  to?: string;
};
