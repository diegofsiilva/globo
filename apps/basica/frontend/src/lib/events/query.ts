/** Peças compartilhadas pelas telas que consultam a API de leitura: o tipo do
 * escopo cumulativo, sua aplicação na query string, o transporte com erros
 * classificados e a consulta de valores possíveis por campo (`/facets`). */

import { apiFetch, API_URL } from "@/lib/api/client";

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

/** Valores distintos por dimensão, para popular os seletores de escopo. */
export type FacetsResponse = { facets: Record<string, string[]> };

/** Aplica somente as chaves preenchidas -- escopo vazio significa "sem recorte". */
export function withScope(params: URLSearchParams, scope: EventScope) {
  for (const [key, value] of Object.entries(scope)) {
    if (value) params.set(key, value);
  }
  return params;
}

/**
 * GET autenticado com erro traduzido para `QuerySourceError`.
 *
 * Delega ao cliente compartilhado: o header `Authorization` e a queda de sessão
 * em 401/403 ficam num lugar só (`lib/api/client.ts`).
 *
 * @param path Caminho na API, começando com `/`.
 * @param params Query string já montada.
 * @param signal Aborta quando a tela desmonta ou o filtro muda.
 * @param reference Prefixo do código de referência mostrado ao operador.
 * @returns O corpo da resposta.
 */
export async function getJson<T>(
  path: string,
  params: URLSearchParams,
  signal: AbortSignal | undefined,
  reference: string,
): Promise<T> {
  // `reference` chega como "ARG-FACETS"; o cliente monta "ARG-<tag>-...".
  const tag = reference.replace(/^ARG-/, "");
  return apiFetch<T>(`${path}?${params}`, { tag, signal });
}

/** Valores existentes para cada campo, usados para montar os filtros de escopo. */
export function fetchFacets(fields: string[], signal?: AbortSignal): Promise<FacetsResponse> {
  const params = new URLSearchParams();
  for (const field of fields) params.append("field", field);
  return getJson<FacetsResponse>("/api/v1/series/facets", params, signal, "ARG-FACETS");
}
