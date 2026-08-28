/** Adapter HTTP da tela Comparar: changes, referências e série temporal. */

import { apiFetch } from "@/lib/api/client";
import type {
  ChangesResponse,
  LastLivePeakResponse,
  StableWindowResponse,
  TimeseriesResponse,
} from "./types";

/**
 * GET autenticado com o tratamento de erro tipado compartilhado.
 *
 * @param path Caminho na API, começando com `/`.
 * @param signal Aborta quando a tela desmonta ou a janela muda.
 * @returns O corpo da resposta.
 */
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return apiFetch<T>(path, { tag: "CMP", signal });
}

/**
 * Deploys e mudanças de configuração na janela.
 *
 * @param from Início da janela, em ISO 8601.
 * @param to Fim da janela, em ISO 8601.
 * @param signal Aborta quando a tela desmonta ou a janela muda.
 * @returns As mudanças ordenadas por início.
 */
export function fetchChanges(
  from: string,
  to: string,
  signal?: AbortSignal,
): Promise<ChangesResponse> {
  const params = new URLSearchParams({ from, to });
  return getJson(`/api/v1/changes?${params}`, signal);
}

/**
 * A janela sem incidente mais recente, para servir de referência "estável".
 *
 * @param durationMinutes Duração pedida.
 * @param signal Aborta quando a tela desmonta.
 * @returns A janela encontrada, ou `found: false` — que é resultado legítimo:
 *   pode não existir período sem incidente daquele tamanho no histórico.
 */
export function fetchStableWindow(
  durationMinutes: number,
  signal?: AbortSignal,
): Promise<StableWindowResponse> {
  const params = new URLSearchParams({ duration_minutes: String(durationMinutes) });
  return getJson(`/api/v1/references/stable-window?${params}`, signal);
}

/**
 * A última transmissão ao vivo, para servir de referência "pico".
 *
 * @param signal Aborta quando a tela desmonta.
 * @returns A janela da transmissão com competição e times, que entram no rótulo
 *   — "pico" sozinho não diz ao operador contra o que ele está comparando.
 */
export function fetchLastLivePeak(signal?: AbortSignal): Promise<LastLivePeakResponse> {
  return getJson(`/api/v1/references/last-live-peak`, signal);
}

/** Série da janela pedida, sobre `gold.v_feature_bucket`.
 *
 * A tela chama uma vez por janela e compara os resultados no cliente, então o
 * `compare=true` da rota antiga não é necessário aqui. */
export async function fetchTimeseries(
  filters: { from: string; to: string; interval: number; metric?: string },
  signal?: AbortSignal,
): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({
    from: filters.from,
    to: filters.to,
    interval: String(filters.interval),
    metric: filters.metric ?? "sessions",
  });
  const bruto = await getJson<{
    interval_minutes: number;
    total: number;
    buckets: {
      bucket: string;
      value: number | null;
      by_metric: Record<string, number | null>;
    }[];
  }>(`/api/v1/series/timeseries?${params}`, signal);

  return {
    interval_minutes: bruto.interval_minutes,
    total: bruto.total,
    buckets: bruto.buckets.map((balde) => ({
      bucket: balde.bucket,
      count: balde.value ?? 0,
      by_event_name: Object.fromEntries(
        Object.entries(balde.by_metric).map(([nome, valor]) => [nome, valor ?? 0]),
      ),
    })),
  };
}
