/** Agrupa hipóteses que dizem a mesma coisa sobre o mesmo escopo. */

import type { Hypothesis } from "./types";

/**
 * Um grupo de ocorrências da mesma hipótese.
 *
 * O motor publica uma hipótese por janela de processamento. Um problema que
 * dura horas vira uma dezena de linhas iguais na lista, e o operador precisa
 * rolar por elas para chegar à próxima hipótese diferente.
 */
export type HypothesisGroup = {
  key: string;
  /** A ocorrência de maior score, que representa o grupo na lista. */
  lead: Hypothesis;
  /** Todas as ocorrências, da mais recente para a mais antiga. */
  items: Hypothesis[];
  /** Primeiro e último efeito do grupo, já formatados; `null` sem instante. */
  firstAt: string | null;
  lastAt: string | null;
};

const dayFormatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });
const timeFormatter = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" });

function formatMoment(epoch: number): string {
  return `${dayFormatter.format(new Date(epoch))} ${timeFormatter.format(new Date(epoch))}`;
}

function instant(hypothesis: Hypothesis): number {
  const epoch = new Date(hypothesis.timelineAnchor).getTime();
  return Number.isFinite(epoch) ? epoch : Number.NEGATIVE_INFINITY;
}

/**
 * Agrupa por família, título e escopo, preservando a ordem da API.
 *
 * A API devolve por score decrescente, então a primeira ocorrência vista de
 * cada grupo é a de maior score: ela vira o `lead`, e os grupos saem na ordem
 * dos seus melhores scores. Nada é descartado — as demais ocorrências ficam em
 * `items` e continuam selecionáveis no painel.
 *
 * @param hypotheses Hipóteses na ordem em que a API as devolveu.
 * @returns Grupos na ordem do melhor score de cada um.
 */
export function groupHypotheses(hypotheses: Hypothesis[]): HypothesisGroup[] {
  const groups = new Map<string, Hypothesis[]>();
  for (const hypothesis of hypotheses) {
    const key = [hypothesis.category, hypothesis.title, hypothesis.segment].join("|");
    const items = groups.get(key);
    if (items) items.push(hypothesis);
    else groups.set(key, [hypothesis]);
  }

  return [...groups.entries()].map(([key, items]) => {
    const dated = items.map(instant).filter(Number.isFinite);
    return {
      key,
      lead: items[0],
      items: [...items].sort((a, b) => instant(b) - instant(a)),
      firstAt: dated.length ? formatMoment(Math.min(...dated)) : null,
      lastAt: dated.length ? formatMoment(Math.max(...dated)) : null,
    };
  });
}
