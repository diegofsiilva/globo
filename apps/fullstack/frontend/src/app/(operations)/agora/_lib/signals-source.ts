/**
 * Adapter HTTP de `GET /api/v1/signals` e `GET /api/v1/series/facets`
 * (tela Agora).
 */

import { apiFetch } from "@/lib/api/client";
import type { OpenDegradation, SignalDeviation, SignalSeverity } from "../_mocks/scenario";

/**
 * Um sinal como `/api/v1/signals` o devolve.
 *
 * `threshold_z` está em desvios-padrão, que o operador não interpreta sem
 * contexto; `threshold_value` é o mesmo limiar convertido de volta à unidade
 * nativa da métrica, do lado em que o desvio está acontecendo.
 *
 * `sessions_impacted` vem `null` por limitação de dado: `gold.feature_bucket`
 * não tem `session_id`, e inventar a atribuição causal seria pior que admitir
 * a ausência.
 */
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

/** Resposta de `/api/v1/signals`, do maior desvio para o menor. */
export type SignalsResponse = {
  items: SignalItem[];
  /** Tamanho de `items`, não um total da base — a consulta não chega a apurá-lo. */
  count: number;
  /** Havia mais sinais acima do limiar do que couberam no `limit`. */
  truncated: boolean;
};

/** Valores distintos por dimensão, para os seletores da tela. */
export type FacetsResponse = { facets: Record<string, string[]> };

/**
 * Recorte aceito pela tela Agora.
 *
 * São as MESMAS dimensões de `gold.v_feature_bucket` que Explorar, Comparar e
 * Recorte usam. A versão anterior desta tela oferecia plataforma, fabricante,
 * região e app — dimensões que existem em `bronze.event`, e não na série
 * agregada que alimenta os sinais. O resultado é que os quatro seletores eram
 * inertes: o operador escolhia um valor e a lista não mudava, sem nada na
 * interface dizendo por quê.
 */
export type SignalScope = {
  source?: string;
  entity?: string;
  metric?: string;
  /** `"true"` / `"false"`; ausente significa "com e sem transmissão". */
  tem_jogo?: string;
};

/**
 * Consulta `/api/v1/signals`.
 *
 * @param scope Recorte a aplicar. Chaves com `"all"` ou vazias são omitidas —
 *   o servidor trata ausência como "sem filtro".
 * @param signal Aborta quando a tela desmonta ou o filtro muda.
 * @returns Sinais ativos, do maior desvio para o menor.
 */
export async function fetchSignals(
  scope: SignalScope = {},
  signal?: AbortSignal,
): Promise<SignalsResponse> {
  const params = new URLSearchParams();
  for (const [chave, valor] of Object.entries(scope)) {
    if (valor && valor !== "all") params.set(chave, valor);
  }
  const query = params.toString();
  return apiFetch(`/api/v1/signals${query ? `?${query}` : ""}`, {
    tag: "SIGNALS",
    signal,
  });
}

/**
 * Consulta os valores reais das dimensões da série, para popular os seletores.
 *
 * Usa `/api/v1/series/facets` e não `/api/v1/facets`: o primeiro lê
 * `gold.v_feature_bucket`, que é a mesma fonte dos sinais. O segundo lê
 * `bronze.event` — as opções viriam de uma tabela que a consulta de sinais não
 * consulta, e ofereceriam recortes que nunca devolvem resultado.
 *
 * @param signal Aborta quando a tela desmonta.
 * @returns Valores distintos por dimensão.
 */
export async function fetchAgoraFacets(signal?: AbortSignal): Promise<FacetsResponse> {
  const params = new URLSearchParams();
  params.append("field", "source");
  params.append("field", "entity");
  params.append("field", "metric");
  params.append("field", "tem_jogo");
  return apiFetch(`/api/v1/series/facets?${params}`, { tag: "FACETS", signal });
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

const compactFormatter = new Intl.NumberFormat("pt-BR", {
  notation: "compact",
  maximumFractionDigits: 2,
});

const BYTE_UNITS = ["B", "KiB", "MiB", "GiB", "TiB"];

/** Métricas cujo valor é uma contagem de bytes (`memory`, `*_bytes`). */
function isByteMetric(metric: string): boolean {
  return /(^|_)(memory|bytes)(_|$)/.test(metric);
}

function formatBytes(value: number): string {
  let scaled = Math.abs(value);
  let unit = 0;
  while (scaled >= 1024 && unit < BYTE_UNITS.length - 1) {
    scaled /= 1024;
    unit += 1;
  }
  return `${value < 0 ? "-" : ""}${formatNumber(scaled)} ${BYTE_UNITS[unit]}`;
}

/**
 * Formata um valor na unidade da sua métrica.
 *
 * A API devolve o número cru. Para memória isso é uma contagem de bytes, e
 * `1.126.974.805,33` contra `1.138.704.534,19` obriga o operador a contar
 * dígitos para descobrir que a diferença é de 11 MiB em 1 GiB. Contagens na
 * casa dos milhões saem em notação compacta pelo mesmo motivo.
 *
 * @param metric Nome da métrica, que é o que indica a unidade.
 * @param value Valor na unidade nativa.
 * @returns Valor legível, com unidade quando ela é conhecida.
 */
export function formatMetricValue(metric: string, value: number): string {
  if (isByteMetric(metric)) return formatBytes(value);
  if (Math.abs(value) >= 1_000_000) return compactFormatter.format(value);
  return formatNumber(value);
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

/**
 * Caminho da tela de Hipóteses já restrita ao sinal.
 *
 * `source` e `entity` são os filtros de evidência que `GET /api/v1/hypotheses`
 * aceita: a lista abre só com as hipóteses que citam esta série.
 */
function hypothesesPath(item: SignalItem): string {
  const params = new URLSearchParams({ source: item.source, entity: item.entity });
  return `/hipoteses?${params}`;
}

/** Converte um sinal da API na forma que a tabela/painel de detalhe espera. */
export function toSignalDeviation(item: SignalItem): SignalDeviation {
  const delta = item.current_value - item.baseline;
  const deltaLabel = `${delta >= 0 ? "+" : ""}${formatMetricValue(item.metric, delta)}`;

  return {
    id: item.id,
    source: item.source,
    metric: item.metric,
    title: item.title,
    severity: item.severity,
    trend: normalizeTrend(item.trend),
    current: formatMetricValue(item.metric, item.current_value),
    baseline: formatMetricValue(item.metric, item.baseline),
    delta: deltaLabel,
    // A lista é ordenada por |z|; sem o número na tela, a ordem parece
    // arbitrária -- um Δ de +1,22 aparece acima de um Δ de -11 MiB.
    zScore: formatNumber(item.z),
    sessions: item.sessions_impacted?.toLocaleString("pt-BR") ?? "não disponível",
    threshold:
      item.threshold_value != null
        ? `${formatMetricValue(item.metric, item.threshold_value)} (z ≥ ${formatNumber(item.threshold_z)})`
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
      // `t` é o que a Timeline lê para centrar a janela; só com `sinal` ela
      // abria na janela que termina agora, com o desvio fora do eixo.
      timeline: `/timeline?sinal=${encodeURIComponent(item.id)}&t=${encodeURIComponent(item.detected_at)}`,
      cut: `/recorte?sinal=${encodeURIComponent(item.id)}`,
      hypotheses: hypothesesPath(item),
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

/**
 * Converte o sinal mais severo no card de degradação ativa.
 *
 * Devolve o nome da métrica junto do valor, e `null` quando não há sessões
 * atribuídas: o card rotulava qualquer valor como "falha de play" e a duração
 * como "sem reclamação aberta", duas afirmações que o sinal não sustenta.
 */
export function toActiveDegradation(item: SignalItem) {
  return {
    title: item.title,
    detectedAt: formatTime(item.detected_at),
    metric: item.metric,
    hypothesesPath: hypothesesPath(item),
    currentValue: formatMetricValue(item.metric, item.current_value),
    impactedSessions: item.sessions_impacted?.toLocaleString("pt-BR") ?? null,
    baselineMultiplier: item.multiplier != null ? `×${formatNumber(item.multiplier)}` : "—",
    openFor: formatDuration(item.time_since_detection_seconds),
  };
}
