/** Peças compartilhadas pelas telas que consultam a API de leitura: o tipo do
 * escopo cumulativo, sua aplicação na query string, o transporte com erros
 * classificados e a consulta de valores possíveis por campo (`/facets`). */

import { QuerySourceError } from "@/lib/operational-state";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

if (!API_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_URL não definida. Rode `make frontend-build` ou exporte a " +
      "variável antes de `next build`.",
  );
}

/** Escopo de filtros cumulativos das telas de investigação.
 *
 * São as dimensões de `gold.v_feature_bucket` (`DIMENSOES` em
 * infrastructure/gold.py), e não mais as colunas de evento por sessão. O
 * escopo antigo (`device_os`, `uf`, `app_version`...) apontava para
 * `silver.session_event`, que este dump não alimenta -- era por isso que o
 * chip PLATAFORMA da tela Agora oferecia o valor `NetRange`. */
export type EventScope = Partial<{
  source: string;
  entity: string;
  metric: string;
  hora_brt: string;
  dow: string;
  tem_jogo: string;
}>;

export type FacetsResponse = { facets: Record<string, string[]> };

/** Aplica somente as chaves preenchidas -- escopo vazio significa "sem recorte". */
export function withScope(params: URLSearchParams, scope: EventScope) {
  for (const [key, value] of Object.entries(scope)) {
    if (value) params.set(key, value);
  }
  return params;
}

/** GET com erro traduzido para `QuerySourceError`, que a moldura sabe exibir. */
export async function getJson<T>(
  path: string,
  params: URLSearchParams,
  signal: AbortSignal | undefined,
  reference: string,
): Promise<T> {
  const endpoint = `${API_URL.replace(/\/$/, "")}${path}?${params}`;
  let response: Response;

  try {
    response = await fetch(endpoint, { signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new QuerySourceError(
      "A conexão com a API de leitura está indisponível. Verifique a rede e tente novamente.",
      "offline",
      `${reference}-OFFLINE`,
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A API excedeu o tempo limite da consulta."
        : `A API respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `${reference}-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new QuerySourceError(
      "A API respondeu em um formato que a interface não reconhece.",
      "invalid-response",
      `${reference}-INVALID-JSON`,
      false,
    );
  }
}

/** Valores existentes para cada campo, usados para montar os filtros de escopo. */
export function fetchFacets(fields: string[], signal?: AbortSignal): Promise<FacetsResponse> {
  const params = new URLSearchParams();
  for (const field of fields) params.append("field", field);
  return getJson<FacetsResponse>("/api/v1/series/facets", params, signal, "ARG-FACETS");
}
