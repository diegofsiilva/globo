/**
 * Transforma a resposta de `GET /api/v1/timeline` no formato que
 * `timeline-content.tsx` já sabe renderizar (`TimelineRow`/`ChronologyEntry`
 * de `_mocks/scenario.ts`).
 *
 * Sem rota própria: `chronology` é montada achatando os pontos das seis
 * raias numa lista só, e `correlationWindow` é derivada do intervalo entre o
 * primeiro e o último ponto com sinal na janela. O campo "Hipótese líder" do
 * card de correlação não tem fonte real disponível aqui (é do motor de
 * hipóteses, fora do escopo desta integração) e fica com um texto explícito
 * em vez de um número inventado.
 */

import type { ChronologyEntry, TimelineRow } from "../_mocks/scenario";
import type {
  DeployPoint,
  IncidentPoint,
  SeriesPoint,
  TimelineApiResponse,
  TimelineLane,
} from "./types";

/** Ordem fixa de exibição das raias, independente da ordem que a API devolve. */
const LANE_ORDER = ["npaw", "prometheus", "newrelic", "apollo", "tsuru", "servicenow"];

/**
 * Rótulo de categoria por fonte, só para leitura (equivalente de exibição ao
 * `CATEGORIA_POR_FONTE` do backend em `application/signals.py`) -- a API não
 * devolve uma categoria de negócio, só o nome comercial da ferramenta.
 */
const LANE_CATEGORY: Record<string, string> = {
  npaw: "Player QoE",
  prometheus: "CDN",
  newrelic: "Backend",
  apollo: "Identidade",
  tsuru: "Deploy",
  servicenow: "Incidentes",
};

type AnyPoint = SeriesPoint | DeployPoint | IncidentPoint;

function pointTimestamp(lane: TimelineLane, point: AnyPoint): string {
  if (lane.lane_type === "series") return (point as SeriesPoint).bucket_ts;
  if (lane.lane_type === "events") return (point as DeployPoint).started_at;
  return (point as IncidentPoint).ts_start;
}

function pointEndTimestamp(lane: TimelineLane, point: AnyPoint): string | null {
  if (lane.lane_type === "events") return (point as DeployPoint).ended_at;
  if (lane.lane_type === "incidents") return (point as IncidentPoint).ts_end;
  return null;
}

/** O ponto mais recente da raia -- é o único que a UI tem espaço pra mostrar por linha. */
function lanePrimaryPoint(lane: TimelineLane): AnyPoint | null {
  if (lane.points.length === 0) return null;
  return [...lane.points].sort(
    (a, b) =>
      new Date(pointTimestamp(lane, b as AnyPoint)).getTime() -
      new Date(pointTimestamp(lane, a as AnyPoint)).getTime(),
  )[0] as AnyPoint;
}

function laneKind(lane: TimelineLane): TimelineRow["kind"] {
  if (lane.points.length === 0) return "empty";
  if (lane.lane_type === "events") return "deploy";
  if (lane.lane_type === "incidents") return "critical";
  return "neutral";
}

function laneEventText(lane: TimelineLane, point: AnyPoint | null): { event: string; detail: string } {
  if (!point) return { event: "sem sinal na janela", detail: "" };

  if (lane.lane_type === "series") {
    const series = point as SeriesPoint;
    return { event: `${series.metric}: ${series.value}`, detail: series.entity };
  }

  if (lane.lane_type === "events") {
    const deploy = point as DeployPoint;
    return {
      event: deploy.target_value ?? deploy.kind ?? "evento de deploy",
      detail: [deploy.kind, deploy.owner].filter(Boolean).join(" · "),
    };
  }

  const incident = point as IncidentPoint;
  return {
    event: incident.ref_id,
    detail: [incident.severity, incident.provenance].filter(Boolean).join(" · "),
  };
}

function percentInWindow(iso: string, windowFrom: number, windowSpan: number): number {
  if (windowSpan <= 0) return 0;
  const t = new Date(iso).getTime();
  return Math.min(100, Math.max(0, ((t - windowFrom) / windowSpan) * 100));
}

function formatHour(t: number): string {
  return new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function formatDay(t: number): string {
  return new Date(t).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/**
 * Dia e hora de um instante, no fuso do navegador.
 *
 * A cronologia mistura dias: um incidente aberto anteontem entra na janela de
 * hoje porque ainda está em curso. Só com `hh:mm`, a lista ordenada por
 * instante lê-se como fora de ordem ("13:59, 12:35, 08:42"), e o operador não
 * tem como saber que são três dias diferentes.
 *
 * @param t Instante em milissegundos.
 * @returns Rótulo `dd/mm hh:mm`.
 */
export function formatMoment(t: number): string {
  return `${formatDay(t)} ${formatHour(t)}`;
}

/**
 * Janela de `minutes` centrada em `anchor`, sem passar do presente virtual.
 *
 * Usada quando a tela é aberta a partir de uma hipótese: o instante dela fica
 * no meio do eixo, com o antes e o depois visíveis. Se metade da janela cairia
 * no futuro do relógio virtual, a janela recua até terminar em `simNow` — as
 * views não devolvem nada além dele.
 *
 * @param anchor Instante que deve ficar em evidência.
 * @param simNow Presente virtual.
 * @param minutes Largura da janela.
 * @returns Limites ISO da janela.
 */
export function windowAround(anchor: Date, simNow: Date, minutes: number) {
  const span = minutes * 60_000;
  const to = Math.min(anchor.getTime() + span / 2, simNow.getTime());
  return { from: new Date(to - span).toISOString(), to: new Date(to).toISOString() };
}

/**
 * Posição de um instante no eixo, em % da janela.
 *
 * @param response Resposta da timeline, que carrega a janela consultada.
 * @param iso Instante a posicionar.
 * @returns Percentual entre 0 e 100, ou `null` quando o instante está fora da
 *   janela ou não é uma data.
 */
export function toMarker(response: TimelineApiResponse, iso: string): number | null {
  const from = new Date(response.window.from).getTime();
  const to = new Date(response.window.to).getTime();
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t) || to <= from || t < from || t > to) return null;
  return ((t - from) / (to - from)) * 100;
}

/** Uma linha por raia, na ordem fixa das seis fontes, com posição calculada contra a janela. */
export function toTimelineRows(response: TimelineApiResponse): TimelineRow[] {
  const windowFrom = new Date(response.window.from).getTime();
  const windowTo = new Date(response.window.to).getTime();
  const span = windowTo - windowFrom;

  const lanesByOrder = LANE_ORDER.map((source) =>
    response.lanes.find((lane) => lane.source === source),
  ).filter((lane): lane is TimelineLane => Boolean(lane));

  return lanesByOrder.map((lane) => {
    const point = lanePrimaryPoint(lane);
    const { event, detail } = laneEventText(lane, point);
    const kind = laneKind(lane);
    const label = LANE_CATEGORY[lane.source] ?? lane.label;

    if (!point) {
      return { label, source: lane.label, event, detail, kind, start: 0, width: 0 };
    }

    const start = percentInWindow(pointTimestamp(lane, point), windowFrom, span);
    const endIso = pointEndTimestamp(lane, point);
    // Sem duração (raia de série), desenha só um marcador pequeno; com
    // duração (deploy/incidente), a largura é a duração normalizada.
    const width = endIso ? Math.max(0.8, percentInWindow(endIso, windowFrom, span) - start) : 1.5;

    return { label, source: lane.label, event, detail, kind, start, width };
  });
}

/** Achata os pontos de todas as raias numa lista cronológica só. */
export function toChronology(response: TimelineApiResponse): ChronologyEntry[] {
  const entries = response.lanes.flatMap((lane) =>
    lane.points.map((point) => {
      const timestamp = new Date(pointTimestamp(lane, point as AnyPoint));
      const { event, detail } = laneEventText(lane, point as AnyPoint);
      return {
        t: timestamp.getTime(),
        hour: formatMoment(timestamp.getTime()),
        source: lane.label.toUpperCase(),
        description: detail ? `${event} · ${detail}` : event,
      };
    }),
  );

  entries.sort((a, b) => a.t - b.t);
  return entries.map(({ hour, source, description }) => ({ hour, source, description }));
}

/**
 * A janela de correlação exibida abaixo das raias.
 *
 * `band` vem `null` quando nenhuma raia tem ponto na janela — nesse caso não há
 * o que destacar, e desenhar uma faixa de largura zero sugeriria um sinal
 * pontual que não existe.
 */
export type CorrelationWindow = {
  label: string;
  description: string;
  /** Posição do destaque no eixo, em % -- null quando não há sinal na janela. */
  band: { start: number; width: number } | null;
  metrics: Array<{ label: string; value: string }>;
};

/**
 * Deriva a "janela de correlação" do intervalo entre o primeiro e o último
 * ponto com sinal na consulta -- não é um cálculo de correlação estatística
 * de verdade, só o span onde há dado, que é o que dá pra sustentar sem o
 * motor de hipóteses.
 */
export function toCorrelationWindow(
  response: TimelineApiResponse,
  hypothesisId?: string | null,
): CorrelationWindow {
  const windowFrom = new Date(response.window.from).getTime();
  const windowTo = new Date(response.window.to).getTime();
  const span = windowTo - windowFrom;

  const timestamps = response.lanes.flatMap((lane) =>
    lane.points.map((point) => new Date(pointTimestamp(lane, point as AnyPoint)).getTime()),
  );
  const sourcesWithSignal = response.lanes.filter((lane) => lane.points.length > 0).length;
  const totalPoints = response.lanes.reduce((sum, lane) => sum + lane.points.length, 0);

  const incidentLane = response.lanes.find((lane) => lane.lane_type === "incidents");
  const firstIncident = incidentLane?.points[0] as IncidentPoint | undefined;

  const metrics: CorrelationWindow["metrics"] = [
    { label: "Fontes com sinal", value: `${sourcesWithSignal} de ${response.lanes.length}` },
    { label: "Pontos correlacionados", value: totalPoints.toLocaleString("pt-BR") },
    {
      label: "1º chamado na janela",
      value: firstIncident ? formatHour(new Date(firstIncident.ts_start).getTime()) : "nenhum",
    },
  ];
  // A hipótese só aparece quando a tela foi aberta a partir de uma: a rota de
  // timeline não conhece o motor, e uma linha fixa dizendo isso expunha ao
  // operador uma limitação de integração em vez de um fato do incidente.
  if (hypothesisId) metrics.push({ label: "Hipótese em análise", value: `#${hypothesisId}` });

  if (timestamps.length === 0) {
    return {
      label: "sem sinal na janela",
      description: "Nenhuma das seis raias teve ponto na janela consultada.",
      band: null,
      metrics,
    };
  }

  const from = Math.min(...timestamps);
  const to = Math.max(...timestamps);

  const sameDay = formatDay(from) === formatDay(to);

  return {
    label: `${formatHour(from)} → ${formatHour(to)}`,
    description:
      (sameDay ? "" : `De ${formatDay(from)} a ${formatDay(to)}. `) +
      "Intervalo entre o primeiro e o último sinal registrado pelas seis raias na janela consultada.",
    band: {
      start: percentInWindow(new Date(from).toISOString(), windowFrom, span),
      width: Math.max(0.5, percentInWindow(new Date(to).toISOString(), windowFrom, span) -
        percentInWindow(new Date(from).toISOString(), windowFrom, span)),
    },
    metrics,
  };
}

/** Cinco marcas igualmente espaçadas no eixo, cobrindo a janela consultada. */
export function toTimeAxis(response: TimelineApiResponse): string[] {
  const from = new Date(response.window.from).getTime();
  const to = new Date(response.window.to).getTime();
  const steps = 5;
  const ticks = Array.from({ length: steps }, (_, index) => from + ((to - from) * index) / (steps - 1));
  // O dia entra na primeira marca e em cada virada: uma janela de 24 h começa
  // e termina na mesma hora, e sem o dia as duas pontas do eixo são iguais.
  return ticks.map((tick, index) =>
    index === 0 || formatDay(tick) !== formatDay(ticks[index - 1])
      ? formatMoment(tick)
      : formatHour(tick),
  );
}
