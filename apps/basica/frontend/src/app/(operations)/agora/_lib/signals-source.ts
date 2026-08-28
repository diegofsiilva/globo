/** Adapter HTTP de `GET /api/v1/signals` e `GET /api/v1/facets` (tela Agora). */

import { QuerySourceError } from "@/lib/operational-state";
import type { OpenDegradation, SignalDeviation, SignalSeverity } from "../_mocks/scenario";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

export type SignalItem = {
  id: string;
  source: string;
  entity: string;
  metric: string;
  title: string;
  current_value: number;
  baseline: number;
  stddev: number;
  multiplier: number | null;
  z: number;
  threshold_z: number;
  threshold_value: number | null;
  severity: SignalSeverity;
  consecutive_buckets_over_threshold: number;
  detected_at: string;
  time_since_detection_seconds: number;
  sessions_impacted: number | null;
  direction: "subindo" | "descendo" | "estavel";
  trend: number[];
};

export type SignalsResponse = { items: SignalItem[] };

export type FacetsResponse = { facets: Record<string, string[]> };

/** Consulta `/api/v1/signals`. Sem parâmetro: o servidor usa a janela padrão (6h). */
export async function fetchSignals(signal?: AbortSignal): Promise<SignalsResponse> {
  return getJson(`${API_URL}/api/v1/signals`, "SIGNALS", signal);
}

/** Consulta os valores reais de plataforma, fabricante, versão de app e UF
 * para os filtros. `uf` vira região no componente (ver `lib/uf-regions.ts`):
 * a série gold/silver não tem coluna de região nomeada, mas tem UF real. */
export async function fetchAgoraFacets(signal?: AbortSignal): Promise<FacetsResponse> {
  const params = new URLSearchParams();
  params.append("field", "device_os");
  params.append("field", "device_manufacturer");
  params.append("field", "app_version");
  params.append("field", "uf");
  return getJson(`${API_URL}/api/v1/facets?${params}`, "FACETS", signal);
}

/** Mesmo padrão de tratamento de erro do adapter de Hipóteses
 * (`hipoteses/_lib/http-source.ts`): offline, timeout, erro de servidor e
 * resposta não-JSON viram `QuerySourceError` tipado, para o `ScreenFrame`
 * decidir o estado operacional. */
async function getJson<T>(url: string, tag: string, signal?: AbortSignal): Promise<T> {
  if (!API_URL) {
    throw new QuerySourceError(
      "NEXT_PUBLIC_API_URL não está configurada.",
      "server",
      `ARG-${tag}-NO-URL`,
      false,
    );
  }

  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new QuerySourceError(
      "A conexão com a API está indisponível. Verifique a rede e tente novamente.",
      "offline",
      `ARG-${tag}-OFFLINE`,
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A API excedeu o tempo limite da consulta."
        : `A API respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `ARG-${tag}-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new QuerySourceError(
      "A API respondeu em um formato que a interface não reconhece.",
      "invalid-response",
      `ARG-${tag}-INVALID-JSON`,
      false,
    );
  }
}

// --------------------------------------------------------------------------- //
// Mapeamento pra forma que os componentes da tela já esperam (SignalDeviation,
// OpenDegradation, vindos de `_mocks/scenario.ts` -- mantidos como o
// "contrato visual" da tela mesmo com o dado agora vindo de verdade).
// --------------------------------------------------------------------------- //

const numberFormatter = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const timeFormatter = new Intl.DateTimeFormat("pt-BR", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return timeFormatter.format(date);
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.round(minutes / 60)} h`;
}

function directionLabel(direction: SignalItem["direction"]): string {
  if (direction === "subindo") return "subindo";
  if (direction === "descendo") return "descendo";
  return "estável";
}

function severityLabelLong(severity: SignalSeverity): string {
  if (severity === "critical") return "crítico";
  if (severity === "warning") return "de atenção";
  return "estável";
}

/** O componente usa o valor do trend direto como altura de barra em px --
 * sem normalizar, uma métrica em ms (ex.: 150) estouraria a barra. Reduz a
 * série bruta pra uma faixa visual fixa, preservando a forma relativa. */
function normalizeTrend(values: number[]): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values.map((value) => Math.round(((value - min) / span) * 30) + 4);
}

/** Converte um sinal da API na forma que a tabela/painel de detalhe espera. */
export function toSignalDeviation(item: SignalItem): SignalDeviation {
  const delta = item.current_value - item.baseline;
  const deltaLabel = `${delta >= 0 ? "+" : ""}${formatNumber(delta)}`;

  return {
    id: item.id,
    source: item.source,
    metric: item.metric,
    title: item.title,
    severity: item.severity,
    trend: normalizeTrend(item.trend),
    current: formatNumber(item.current_value),
    baseline: formatNumber(item.baseline),
    delta: deltaLabel,
    sessions: item.sessions_impacted?.toLocaleString("pt-BR") ?? "não disponível",
    threshold:
      item.threshold_value != null
        ? `${formatNumber(item.threshold_value)} (z ≥ ${formatNumber(item.threshold_z)})`
        : `z ≥ ${formatNumber(item.threshold_z)} (desvio-padrão)`,
    detectedAt: formatTime(item.detected_at),
    // O backend não devolve o instante do ÚLTIMO ponto observado separado
    // do instante de detecção -- reusa o mesmo valor (gap documentado).
    lastObservedAt: formatTime(item.detected_at),
    // gold.feature_bucket não tem dimensão de dispositivo/região -- `entity`
    // é a aproximação mais próxima que o backend oferece hoje (gap
    // documentado: filtro de escopo não filtra esta consulta).
    scope: item.entity,
    interpretation:
      `${item.metric} de ${item.entity} (${item.source}) está ${directionLabel(item.direction)}, ` +
      `desvio ${severityLabelLong(item.severity)} há ${item.consecutive_buckets_over_threshold} ` +
      `bucket(s) seguido(s) acima do limiar.`,
    relatedPaths: {
      timeline: `/timeline?sinal=${item.id}`,
      cut: `/recorte?sinal=${item.id}`,
    },
  };
}

/** Converte um sinal (que não é o mais severo) na forma da lista "outras
 * degradações abertas". Sinais `stable` não entram -- não são degradação. */
export function toOpenDegradation(item: SignalItem): OpenDegradation {
  return {
    id: item.id,
    title: item.title,
    description: `${item.metric} de ${item.entity} (${item.source}), z=${formatNumber(item.z)}.`,
    scope: item.entity,
    severity: item.severity === "critical" ? "alto" : "atenção",
    source: item.source,
    openedAt: formatTime(item.detected_at),
  };
}

/** Converte o sinal mais severo no card de degradação ativa. */
export function toActiveDegradation(item: SignalItem) {
  return {
    title: item.title,
    detectedAt: formatTime(item.detected_at),
    failureRate: formatNumber(item.current_value),
    impactedSessions: item.sessions_impacted?.toLocaleString("pt-BR") ?? "não disponível",
    baselineMultiplier: item.multiplier != null ? `×${formatNumber(item.multiplier)}` : "—",
    openFor: formatDuration(item.time_since_detection_seconds),
  };
}
