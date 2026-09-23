/** Adapter HTTP da tela Explorar: breakdown e timeseries. */

import { getJson, withScope, type EventScope } from "@/lib/events/query";

export type { EventScope };

/**
 * Um grupo do agrupamento, já normalizado para o que a tela desenha.
 *
 * `average_duration_ms` vem sempre `null`: `gold.feature_bucket` guarda valor
 * por métrica, não duração por evento. O campo permanece no tipo porque a coluna
 * existe na tabela da tela — exibir "—" é honesto, remover a coluna esconderia
 * uma limitação do dado.
 */
export type BreakdownGroup = {
  key: string;
  count: number;
  share: number;
  average_duration_ms: number | null;
};

/** Agrupamento por uma dimensão da série, com o total da janela. */
export type BreakdownResponse = {
  dimension: string;
  total: number;
  groups: BreakdownGroup[];
};

/** Forma crua devolvida por `/api/v1/series/breakdown`. */
type SeriesBreakdownResponse = {
  dimension: string;
  metric: string | null;
  total: number;
  groups: { key: string; value: number | null; points: number; share: number }[];
};

/** Forma crua devolvida por `/api/v1/series/timeseries`. */
type SeriesTimeseriesResponse = {
  interval_minutes: number;
  metric: string | null;
  total: number;
  buckets: {
    bucket: string;
    value: number | null;
    points: number;
    by_metric: Record<string, number | null>;
  }[];
};

/**
 * Um balde da série temporal.
 *
 * `by_event_name` mantém o nome herdado da versão que lia evento por sessão. No
 * dado agregado a chave é a MÉTRICA (`sessions`, `error_rate_pct`, `p95_ms`);
 * o adapter faz a tradução para que os componentes da tela não mudassem junto
 * com a fonte.
 */
export type TimeseriesBucket = {
  bucket: string;
  count: number;
  by_event_name: Record<string, number>;
};

/** Série temporal em baldes regulares, com o total da janela. */
export type TimeseriesResponse = {
  interval_minutes: number;
  total: number;
  buckets: TimeseriesBucket[];
};

/**
 * Agrupa a série por uma dimensão.
 *
 * @param dimension Dimensão do agrupamento (`source`, `entity`, `metric`,
 *   `hora_brt`, `dow`).
 * @param window Janela consultada, em ISO 8601.
 * @param scope Recorte cumulativo; chaves vazias não entram na query string.
 * @param signal Aborta quando a tela desmonta ou o filtro muda.
 * @returns Os grupos ordenados pelo servidor, com o total.
 */
export async function fetchBreakdown(
  dimension: string,
  window: { from: string; to: string },
  scope: EventScope,
  signal?: AbortSignal,
): Promise<BreakdownResponse> {
  const params = withScope(
    new URLSearchParams({ dimension, from: window.from, to: window.to, limit: "100" }),
    scope,
  );
  const bruto = await getJson<SeriesBreakdownResponse>(
    "/api/v1/series/breakdown",
    params,
    signal,
    "ARG-EXP-BREAKDOWN",
  );
  return {
    dimension: bruto.dimension,
    total: bruto.total,
    groups: bruto.groups.map((grupo) => ({
      key: grupo.key,
      count: grupo.value ?? 0,
      share: grupo.share,
      // A serie agregada nao carrega duracao media -- `gold.feature_bucket`
      // guarda valor por metrica, nao duracao por evento.
      average_duration_ms: null,
    })),
  };
}

/**
 * Série temporal agregada da janela.
 *
 * @param window Janela consultada, em ISO 8601.
 * @param intervalMinutes Largura de cada balde.
 * @param scope Recorte cumulativo.
 * @param signal Aborta quando a tela desmonta ou o filtro muda.
 * @returns Os baldes com o valor total e a quebra por métrica.
 */
export async function fetchTimeseries(
  window: { from: string; to: string },
  intervalMinutes: number,
  scope: EventScope,
  signal?: AbortSignal,
): Promise<TimeseriesResponse> {
  const params = withScope(
    new URLSearchParams({ from: window.from, to: window.to, interval: String(intervalMinutes) }),
    scope,
  );
  const bruto = await getJson<SeriesTimeseriesResponse>(
    "/api/v1/series/timeseries",
    params,
    signal,
    "ARG-EXP-TIMESERIES",
  );
  return {
    interval_minutes: bruto.interval_minutes,
    total: bruto.total,
    buckets: bruto.buckets.map((balde) => ({
      bucket: balde.bucket,
      count: balde.value ?? 0,
      // A tela indexa esse mapa pelo "tipo" selecionado; no dado agregado o
      // eixo equivalente e a METRICA (sessions, error_rate_pct, p95_ms...).
      by_event_name: Object.fromEntries(
        Object.entries(balde.by_metric).map(([nome, valor]) => [nome, valor ?? 0]),
      ),
    })),
  };
}
