/** Cenário fixo da tela de Hipóteses (artefatos/entendimento_ux.md §5.3.4).
 *
 * Invariante que o backend precisa manter quando existir: em cada hipótese os
 * pesos somam 1 e as contribuições somam o score. É o que autoriza a tela a
 * apresentar o score como decomponível.
 */

import type { HypothesesReport } from "@/lib/hypotheses/api";

export const hypothesesScenario: HypothesesReport = {
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
