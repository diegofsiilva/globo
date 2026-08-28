/** Formato de `GET /api/v1/timeline` (seis raias de fonte). */

/** Um ponto de uma raia de métrica (NPAW, Prometheus, New Relic, Apollo). */
export type SeriesPoint = {
  bucket_ts: string;
  entity: string;
  metric: string;
  value: number;
};

/** Um deploy na raia do Tsuru. Tem duração, e não só um instante. */
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

/** Um incidente na raia do ServiceNow, com início, fim, veredito e gravidade. */
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

/**
 * Campos comuns às três formas de raia.
 *
 * `truncated` avisa que a raia passou do teto de entradas por raia. Nas raias
 * de SÉRIE os pontos são amostrados em passo uniforme e continuam cobrindo a
 * janela inteira -- cortar o excedente deixaria uma lacuna no gráfico onde há
 * dado. Nas raias de EVENTO o excedente é cortado em ordem cronológica, porque
 * amostrar evento discreto omitiria incidentes reais sem indicação na tela.
 */
type LaneBase = {
  source: string;
  label: string;
  /** Quantas entradas vieram nesta raia. */
  count: number;
  truncated: boolean;
};

/**
 * Uma das seis raias.
 *
 * União discriminada por `lane_type`: forçar deploy e incidente no formato de
 * série temporal perderia duração, motivo e gravidade.
 */
export type TimelineLane =
  | (LaneBase & { lane_type: "series"; points: SeriesPoint[] })
  | (LaneBase & { lane_type: "events"; points: DeployPoint[] })
  | (LaneBase & { lane_type: "incidents"; points: IncidentPoint[] });

/** Resposta de `/api/v1/timeline`: a janela efetiva e as seis raias. */
export type TimelineApiResponse = {
  window: { from: string; to: string };
  /** Teto aplicado a cada raia, para a interface poder explicar o truncamento. */
  limit_per_lane: number;
  /** Verdadeiro se QUALQUER raia foi reduzida. */
  truncated: boolean;
  lanes: TimelineLane[];
};

/** Recorte pedido. Vazio deixa o servidor usar as 3 h antes de `sim.now()`. */
export type TimelineQuery = {
  from?: string;
  to?: string;
};
