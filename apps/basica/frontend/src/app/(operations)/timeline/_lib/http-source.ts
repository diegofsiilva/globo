/** Adapter HTTP de `GET /api/v1/timeline`. */

import { apiFetch } from "@/lib/api/client";
import type { TimelineApiResponse, TimelineQuery } from "./types";

/**
 * Busca as seis raias de fonte para a janela pedida (ou a janela padrão do
 * servidor, que são as 3 h antes de `sim.now()`).
 *
 * Cada raia vem com no máximo 100 entradas e sinaliza `truncated`. As raias de
 * série são amostradas em passo uniforme e continuam cobrindo a janela inteira;
 * as de deploy e incidente são truncadas em ordem cronológica.
 *
 * @param query Recorte temporal.
 * @param signal Aborta quando a tela desmonta ou a janela muda.
 * @returns As seis raias e a janela efetivamente usada.
 */
export async function fetchTimeline(
  query: TimelineQuery = {},
  signal?: AbortSignal,
): Promise<TimelineApiResponse> {
  const params = new URLSearchParams();
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);

  const qs = params.toString();
  return apiFetch(`/api/v1/timeline${qs ? `?${qs}` : ""}`, { tag: "TL", signal });
}
