/** Tipos do adapter HTTP da tela Comparar. */

export type ReferenceId = "ontem" | "semana" | "estavel" | "pico";

/** Um balde da série temporal, com a quebra opcional por métrica. */
export type TimeseriesBucket = {
  bucket: string;
  count: number;
  by_event_name?: Record<string, number>;
};

/**
 * Resposta de `/api/v1/series/timeseries`.
 *
 * `previous` e `change` só vêm quando a consulta pede comparação. A tela
 * Comparar não os usa: ela consulta duas janelas separadamente e compara no
 * cliente, o que permite âncoras que a rota não sabe calcular sozinha.
 */
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

/** Um deploy ou mudança de configuração, como `/api/v1/changes` devolve. */
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

/** Página de mudanças na janela consultada. */
export type ChangesResponse = { items: ChangeEvent[] };

/**
 * Resposta de `/api/v1/references/stable-window`.
 *
 * `found: false` é resultado legítimo, e não erro: pode não existir janela da
 * duração pedida sem incidente no histórico disponível.
 */
export type StableWindowResponse = { found: boolean; from?: string; to?: string };

/**
 * Resposta de `/api/v1/references/last-live-peak`: a última transmissão ao vivo.
 *
 * Os campos de competição e times entram no rótulo mostrado ao operador --
 * "pico" sozinho não diz contra o que ele está comparando.
 */
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

/**
 * Um ponto do gráfico de comparação, já com as duas séries alinhadas por hora.
 *
 * `outside` marca a hora que existe numa janela e não na outra. Precisa ser
 * desenhada de forma distinta: um zero ali seria lido como queda a zero, e não
 * como ausência de dado.
 */
export type ChartBucket = {
  hour: string;
  now: number;
  reference: number;
  outside?: boolean;
};

/** Uma mudança posicionada na hora correspondente do gráfico. */
export type WindowChange = {
  hour: string;
  description: string;
};
