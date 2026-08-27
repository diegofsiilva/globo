/** Resolve cada referência de comparação numa janela [from, to) real. */

import { fetchLastLivePeak, fetchStableWindow } from "./http-source";
import type { ReferenceId, ResolvedReference } from "./types";

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * "Ontem" e "semana passada" são só a mesma janela deslocada no calendário --
 * não existe rota pra isso, é aritmética de data no cliente. "Estável" e
 * "pico ao vivo anterior" dependem do backend descobrir a janela.
 */
export async function resolveReference(
  id: ReferenceId,
  current: { from: string; to: string },
  signal?: AbortSignal,
): Promise<ResolvedReference> {
  const currentFrom = new Date(current.from);
  const currentTo = new Date(current.to);
  const durationMs = currentTo.getTime() - currentFrom.getTime();

  if (id === "ontem" || id === "semana") {
    const offsetMs = id === "ontem" ? DAY_MS : DAY_MS * 7;
    const from = new Date(currentFrom.getTime() - offsetMs);
    const to = new Date(currentTo.getTime() - offsetMs);
    return {
      from: from.toISOString(),
      to: to.toISOString(),
      detail: formatDetail(from, to),
      found: true,
    };
  }

  if (id === "estavel") {
    const durationMinutes = Math.max(1, Math.round(durationMs / 60_000));
    const result = await fetchStableWindow(durationMinutes, signal);
    if (!result.found || !result.from || !result.to) {
      return { from: "", to: "", detail: "nenhuma janela estável encontrada", found: false };
    }
    return {
      from: result.from,
      to: result.to,
      detail: formatDetail(new Date(result.from), new Date(result.to)),
      found: true,
    };
  }

  // id === "pico"
  const result = await fetchLastLivePeak(signal);
  if (!result.found || !result.from || !result.to) {
    return { from: "", to: "", detail: "nenhuma transmissão ao vivo anterior encontrada", found: false };
  }
  const confronto = result.team_home && result.team_away ? `${result.team_home} x ${result.team_away}` : result.competition;
  return {
    from: result.from,
    to: result.to,
    detail: confronto ? `${formatDetail(new Date(result.from), new Date(result.to))} · ${confronto}` : formatDetail(new Date(result.from), new Date(result.to)),
    found: true,
  };
}

function formatDetail(from: Date, to: Date): string {
  const day = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" }).format(from);
  const hour = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(from);
  const hourTo = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(to);
  return `${day} · ${hour}–${hourTo}`;
}
