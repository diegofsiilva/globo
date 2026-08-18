/** Cliente tipado do relatório de hipóteses de causa provável.
 *
 * Ainda não existe endpoint de hipóteses: a API atual expõe eventos brutos
 * (lib/events-api.ts) e nada que correlacione deploy, borda, autorização e
 * incidentes. Enquanto ele não existe, os dados vêm do cenário fixo no fim
 * deste arquivo -- mas o contrato exportado aqui é o que o backend deve
 * devolver, e o único ponto que muda na integração é `fetchHypotheses`.
 *
 * Para integrar: defina NEXT_PUBLIC_HYPOTHESES_API_URL antes do build. Sem a
 * variável a tela cai no cenário fixo em vez de quebrar, porque o mock também
 * é o material de demonstração do fluxo 01 Agora -> 04 Hipóteses -> 05 Timeline.
 */

const API_URL = process.env.NEXT_PUBLIC_HYPOTHESES_API_URL ?? "";

/** Fator ponderado que compõe o score de uma hipótese. */
export type HypothesisFactor = {
  /** Identificador estável do fator, usado como chave de render. */
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
  /** Domínio responsável, ex.: "Player / build". Exibido em caixa alta. */
  category: string;
  /** Enunciado da causa provável. */
  title: string;
  /** Score de 0 a 100: soma ponderada de `factors`. */
  score: number;
  /** Confiança declarada pelo motor, exibida junto do score. */
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
  /** Evidência que derrubou a hipótese. */
  reason: string;
};

/** Filtro aplicado ao recorte, exibido como chip na barra de escopo. */
export type ScopeChip = {
  id: string;
  /** Dimensão filtrada, ex.: "plataforma". */
  label: string;
  /** Valor selecionado, ex.: "webOS 3.x". */
  value: string;
};

/** Relatório completo devolvido pelo motor de hipóteses. */
export type HypothesesReport = {
  /** Janela analisada. `label` é o texto curto exibido no cabeçalho. */
  window: { from: string; to: string; label: string };
  /** Quantidade de hipóteses geradas, incluindo as que vieram na lista. */
  generated: number;
  /** Quantidade avaliada e descartada, incluindo as não detalhadas. */
  discarded: number;
  scope: ScopeChip[];
  /** Volumetria do recorte, exibida à direita da barra de escopo. */
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
 * mostra a força -- é ela que o operador precisa para discordar de um fator
 * sem descartar a hipótese inteira.
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
  const from = filters.from ?? SCENARIO.window.from;
  const to = filters.to ?? SCENARIO.window.to;
  return { ...SCENARIO, window: { from, to, label: windowLabel(from, to) } };
}

/** Formata a janela como "20:00-20:11" no fuso do navegador. */
function windowLabel(from: string, to: string): string {
  const time = (value: string) =>
    new Date(value).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${time(from)}–${time(to)}`;
}

/**
 * Cenário de referência da documentação (artefatos/entendimento_ux.md §5.3.4).
 *
 * Invariante que a API precisa manter: em cada hipótese os pesos somam 1 e as
 * contribuições somam o score. É o que autoriza a tela a apresentar o score
 * como decomponível.
 */
const SCENARIO: HypothesesReport = {
  window: { from: "2026-08-18T23:00:00Z", to: "2026-08-18T23:11:00Z", label: "20:00–20:11" },
  generated: 4,
  discarded: 11,
  scope: [
    { id: "plataforma", label: "plataforma", value: "webOS 3.x" },
    { id: "fabricante", label: "fabricante", value: "LG" },
    { id: "regiao", label: "região", value: "Nordeste" },
    { id: "app", label: "app", value: "2026.3.0" },
  ],
  summary: { sessions: 41_209, trafficShare: 3.1, sources: 6 },
  hypotheses: [
    {
      id: "player-build",
      category: "Player / build",
      title: "Rollout 2026.3.0 quebrou o fallback DASH→HLS em webOS 3.x",
      score: 87,
      confidence: "alta",
      timelineAnchor: "2026-08-18T22:58:12Z",
      segment: "webos-3x-lg-nordeste-2026.3.0",
      factors: [
        {
          id: "temporal",
          label: "Coincidência temporal com deploy",
          weight: 0.32,
          contribution: 29.4,
          rationale:
            "Tsuru registra deploy do build às 19:58. Desvio começa às 20:04 — 6 min, dentro da janela de propagação típica (4–9 min).",
        },
        {
          id: "especificidade",
          label: "Especificidade do recorte",
          weight: 0.28,
          contribution: 25.1,
          rationale:
            "94% dos erros vêm de 3,1% do tráfego. O recorte casa exatamente com a condição de fallback: webOS ≤ 3.9 sem suporte a DRM live.",
        },
        {
          id: "concorrente",
          label: "Ausência de causa concorrente",
          weight: 0.22,
          contribution: 18.0,
          rationale:
            "CDN, Globo-ID e backend sem desvio no mesmo intervalo e nas mesmas UFs. Nenhum evento de borda no Cloud Armor.",
        },
        {
          id: "precedente",
          label: "Precedente histórico",
          weight: 0.18,
          contribution: 14.5,
          rationale:
            "ServiceNow INC0492117 (mar/2026): mesmo sintoma, mesmo recorte, causa fechada como regressão de player.",
        },
      ],
      evidence: [
        { source: "tsuru_event", detail: "deploy globoplay-tv · 19:58:12" },
        { source: "live_error_attr_hourly", detail: "dash_shaka_playback:6_6002 · 38.774 erros" },
        { source: "geo_hourly", detail: "9 UFs · NE concentra 71%" },
        { source: "incidents", detail: "INC0492117 · similaridade 0,81" },
      ],
    },
    {
      id: "cdn-pop",
      category: "CDN",
      title: "Degradação de tier 2 no PoP de Fortaleza afetando segmentos live",
      score: 64,
      confidence: "média",
      timelineAnchor: "2026-08-18T23:02:00Z",
      segment: "nordeste-pop-fortaleza",
      factors: [
        {
          id: "geografia",
          label: "Concentração geográfica",
          weight: 0.3,
          contribution: 21.6,
          rationale:
            "71% das sessões afetadas estão no Nordeste, região servida majoritariamente pelo PoP de Fortaleza.",
        },
        {
          id: "borda",
          label: "Correlação com métrica de borda",
          weight: 0.28,
          contribution: 19.4,
          rationale:
            "p95 do tempo até o primeiro byte sobe de 180 ms para 402 ms às 20:02, dois minutos antes da primeira falha de play.",
        },
        {
          id: "temporal",
          label: "Coincidência temporal",
          weight: 0.24,
          contribution: 13.2,
          rationale:
            "A subida na borda precede o desvio, mas o mesmo PoP serve VOD sem erro no intervalo.",
        },
        {
          id: "precedente",
          label: "Precedente histórico",
          weight: 0.18,
          contribution: 9.8,
          rationale:
            "INC0448903 (jan/2026): degradação no mesmo PoP, porém com impacto uniforme entre plataformas.",
        },
      ],
      evidence: [
        { source: "edge_latency_5m", detail: "TTFB p95 · 180 ms → 402 ms" },
        { source: "geo_hourly", detail: "CE · 38% das sessões afetadas" },
        { source: "cdn_status", detail: "sem incidente aberto no provedor" },
        { source: "incidents", detail: "INC0448903 · similaridade 0,44" },
      ],
    },
    {
      id: "globo-id",
      category: "Globo-ID",
      title: "Saturação de autorização elevando o tempo de início de play",
      score: 41,
      confidence: "baixa",
      timelineAnchor: "2026-08-18T22:47:00Z",
      segment: "auth-webos-3x",
      factors: [
        {
          id: "startup",
          label: "Correlação com tempo de início de play",
          weight: 0.34,
          contribution: 15.3,
          rationale:
            "p95 do início de play sobe 1,4 s no recorte, mas a curva já subia antes do deploy.",
        },
        {
          id: "temporal",
          label: "Coincidência temporal",
          weight: 0.26,
          contribution: 10.7,
          rationale: "Pico de chamadas de autorização às 19:47, dezessete minutos antes do desvio.",
        },
        {
          id: "especificidade",
          label: "Especificidade do recorte",
          weight: 0.22,
          contribution: 8.6,
          rationale:
            "Erros de autorização aparecem em todas as plataformas, não apenas em webOS 3.x.",
        },
        {
          id: "precedente",
          label: "Precedente histórico",
          weight: 0.18,
          contribution: 6.4,
          rationale: "Sem incidente equivalente nos últimos doze meses.",
        },
      ],
      evidence: [
        { source: "authz_latency_1m", detail: "p95 · 620 ms → 1.980 ms" },
        { source: "live_error_attr_hourly", detail: "auth_denied · 1.204 erros" },
        { source: "session_start_p95", detail: "+1,4 s no recorte" },
        { source: "incidents", detail: "nenhum precedente com similaridade > 0,3" },
      ],
    },
    {
      id: "encoder-origem",
      category: "Encoder / origem",
      title: "Falha de empacotamento no sinal ao vivo",
      score: 23,
      confidence: "baixa",
      timelineAnchor: "2026-08-18T23:04:00Z",
      segment: "live-canal-principal",
      factors: [
        {
          id: "abrangencia",
          label: "Abrangência do sintoma",
          weight: 0.34,
          contribution: 8.1,
          rationale:
            "Falha de empacotamento atingiria todas as plataformas no mesmo canal; 96,9% do tráfego segue normal.",
        },
        {
          id: "temporal",
          label: "Coincidência temporal",
          weight: 0.26,
          contribution: 6.2,
          rationale: "Nenhum evento de reinício de encoder registrado na janela.",
        },
        {
          id: "origem",
          label: "Correlação com a origem",
          weight: 0.22,
          contribution: 5.3,
          rationale: "Manifestos servidos pela origem respondem 200 em todas as amostras coletadas.",
        },
        {
          id: "precedente",
          label: "Precedente histórico",
          weight: 0.18,
          contribution: 3.4,
          rationale: "INC0501774 (jun/2026) teve assinatura distinta: erro 3_3007, não 6_6002.",
        },
      ],
      evidence: [
        { source: "encoder_health", detail: "sem reinício · uptime 41 h" },
        { source: "origin_manifest", detail: "200 em 100% das amostras" },
        { source: "live_error_attr_hourly", detail: "3_3007 · 0 erros" },
        { source: "incidents", detail: "INC0501774 · similaridade 0,12" },
      ],
    },
  ],
  discardedHypotheses: [
    {
      id: "ddos",
      score: 14,
      title: "DDoS / bloqueio de borda",
      reason: "Cloud Armor sem picos de bloqueio na janela.",
    },
    {
      id: "cms",
      score: 11,
      title: "Falha de CMS / metadados",
      reason: "Catálogo respondendo normalmente para o mesmo conteúdo em outras plataformas.",
    },
    {
      id: "sazonalidade",
      score: 8,
      title: "Sazonalidade de pico",
      reason: "Volume 12% abaixo do mesmo horário na semana passada.",
    },
  ],
};
