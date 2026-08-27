/** Tipos do adapter HTTP da tela Comparar. */

export type ReferenceId = "ontem" | "semana" | "estavel" | "pico";

export type TimeseriesBucket = {
  bucket: string;
  count: number;
  by_event_name?: Record<string, number>;
};

export type TimeseriesResponse = {
  interval_minutes: number;
  total: number;
  buckets: TimeseriesBucket[];
  previous?: {
    from: string;
    to: string;
    total: number;
    buckets: Array<{ bucket: string; count: number }>;
  };
  change?: { absolute: number; ratio: number | null };
};

export type ChangeEvent = {
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

export type ChangesResponse = { items: ChangeEvent[] };

export type StableWindowResponse = { found: boolean; from?: string; to?: string };

export type LastLivePeakResponse = {
  found: boolean;
  event_key?: string;
  from?: string;
  to?: string;
  competition?: string;
  team_home?: string;
  team_away?: string;
};

/** Uma referência resolvida: a janela [from, to) e o rótulo pronto pra exibir. */
export type ResolvedReference = {
  from: string;
  to: string;
  detail: string;
  found: boolean;
};

export type ChartBucket = {
  hour: string;
  now: number;
  reference: number;
  outside?: boolean;
};

export type WindowChange = {
  hour: string;
  description: string;
};
