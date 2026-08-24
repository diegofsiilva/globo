/** Cliente tipado do relatório de hipóteses de causa provável.
 *
 * Ainda não existe endpoint de hipóteses: a API atual expõe eventos brutos
 * (lib/events/api.ts) e nada que correlacione deploy, borda, autorização e
 * incidentes. Enquanto ele não existe, os dados vêm de `mocks/hipoteses.ts` --
 * mas o contrato exportado aqui é o que o backend deve devolver, e o único
 * ponto que muda na integração é `fetchHypotheses`.
 *
 * Para integrar: defina NEXT_PUBLIC_HYPOTHESES_API_URL antes do build. Sem a
 * variável a tela cai no cenário fixo em vez de quebrar, porque o mock também
 * é o material de demonstração do fluxo 01 Agora -> 04 Hipóteses -> 05 Timeline.
 */

import { hypothesesScenario } from "@/mocks/hipoteses";

const API_URL = process.env.NEXT_PUBLIC_HYPOTHESES_API_URL ?? "";

/** Fator ponderado que compõe o score de uma hipótese. */
export type HypothesisFactor = {
  id: string;
  /** Nome exibido do fator, ex.: "Coincidência temporal com deploy". */
  label: string;
  /** Peso do fator no score, entre 0 e 1. A soma dos pesos fecha em 1. */
  weight: number;
  /** Pontos que o fator entrega ao score. A soma das contribuições é o score. */
  contribution: number;
  /** Frase que justifica a contribuição, com o dado que a sustenta. */
  rationale: string;
};

/** Fonte de evidência consultada para montar uma hipótese. */
export type EvidenceSource = {
  /** Nome técnico da fonte, ex.: "tsuru_event". */
  source: string;
  /** Trecho do que foi encontrado nela, já formatado para leitura. */
  detail: string;
};

/** Hipótese de causa provável, ranqueada por score. */
export type Hypothesis = {
  id: string;
  /** Domínio responsável, ex.: "Player / build". */
  category: string;
  title: string;
  /** Score de 0 a 100: soma ponderada de `factors`. */
  score: number;
  confidence: "alta" | "média" | "baixa";
  factors: HypothesisFactor[];
  evidence: EvidenceSource[];
  /** Instante que a timeline deve centralizar ao receber esta hipótese. */
  timelineAnchor: string;
  /** Recorte afetado, no formato que a tela 06 usa para se filtrar. */
  segment: string;
};

/** Hipótese avaliada e rejeitada, com o motivo do descarte. */
export type DiscardedHypothesis = {
  id: string;
  /** Score obtido antes do descarte. Mantido para justificar a ordem. */
  score: number;
  title: string;
  reason: string;
};

/** Filtro aplicado ao recorte, exibido na barra de escopo. */
export type ScopeChip = {
  id: string;
  label: string;
  value: string;
};

/** Relatório completo devolvido pelo motor de hipóteses. */
export type HypothesesReport = {
  window: { from: string; to: string; label: string };
  /** Hipóteses geradas, incluindo as que vieram na lista. */
  generated: number;
  /** Avaliadas e descartadas, incluindo as não detalhadas. */
  discarded: number;
  scope: ScopeChip[];
  summary: { sessions: number; trafficShare: number; sources: number };
  hypotheses: Hypothesis[];
  discardedHypotheses: DiscardedHypothesis[];
};

/** Filtros aceitos pelo relatório, espelhando a query string da API. */
export type HypothesesFilters = {
  from?: string;
  to?: string;
  /** Pares dimensão/valor equivalentes aos chips da barra de escopo. */
  scope?: Record<string, string>;
};

/**
 * Consulta o relatório de hipóteses da janela e do recorte informados.
 * @param filters Janela e dimensões do recorte enviadas como query string.
 * @param signal Sinal opcional para cancelar a requisição HTTP.
 * @returns Hipóteses ranqueadas, descartes e metadados do recorte.
 * @throws Error quando a API responde com um status HTTP não bem-sucedido.
 */
export async function fetchHypotheses(
  filters: HypothesesFilters = {},
  signal?: AbortSignal,
): Promise<HypothesesReport> {
  if (!API_URL) return mockReport(filters);

  const params = new URLSearchParams();
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);
  for (const [key, value] of Object.entries(filters.scope ?? {})) params.set(key, value);

  const response = await fetch(`${API_URL}/api/v1/hypotheses?${params}`, { signal });
  if (!response.ok) throw new Error(`A API respondeu com status ${response.status}`);
  return response.json();
}

/**
 * Retorna o quanto o fator sustenta a hipótese, independente do seu peso.
 *
 * Existe porque comparar contribuições brutas mistura duas coisas: um fator
 * pode contribuir pouco por ser fraco ou por pesar pouco. A barra do painel
 * mostra a força -- é ela que permite discordar de um fator sem descartar a
 * hipótese inteira.
 * @param factor Fator já pontuado pelo motor.
 * @returns Força do fator entre 0 e 1.
 */
export function factorStrength(factor: HypothesisFactor): number {
  if (factor.weight <= 0) return 0;
  return Math.min(1, factor.contribution / (factor.weight * 100));
}

/**
 * Monta o relatório do cenário fixo, ecoando a janela pedida.
 *
 * O ranking não varia com os filtros: sem backend, fingir que varia esconderia
 * do próximo desenvolvedor que nada aqui é calculado.
 * @param filters Janela solicitada pela tela.
 * @returns Cópia do cenário com a janela ajustada.
 */
function mockReport(filters: HypothesesFilters): HypothesesReport {
  const from = filters.from ?? hypothesesScenario.window.from;
  const to = filters.to ?? hypothesesScenario.window.to;
  return { ...hypothesesScenario, window: { from, to, label: windowLabel(from, to) } };
}

/** Formata a janela como "20:00–20:11" no fuso do navegador. */
function windowLabel(from: string, to: string): string {
  const time = (value: string) =>
    new Date(value).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${time(from)}–${time(to)}`;
}
