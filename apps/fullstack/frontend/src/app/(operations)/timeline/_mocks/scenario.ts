/** Cenário fixo da tela 05 — Timeline (artefatos/entendimento_ux.md §5.3.5).
 *
 * Portado da implementação de origem (branch docs/relatorio-front). Os dados
 * descrevem a mesma janela do cenário de Hipóteses: deploy às 19:58, subida de
 * p95 na borda às 20:02, primeira falha de play às 20:04.
 */

/** Raia de uma fonte sobre o eixo temporal. */
export type TimelineRow = {
  /** Nome da raia, ex.: "Player QoE". */
  label: string;
  /** Ferramenta que originou o dado. */
  source: string;
  /** Fato registrado na janela. */
  event: string;
  detail: string;
  /** Peso visual do fato: destaque, neutro ou ausência de sinal. */
  kind: "deploy" | "critical" | "neutral" | "empty";
  /** Posição no eixo, em porcentagem da largura da faixa. */
  start: number;
  /** Duração no eixo, em porcentagem. Zero desenha só o rótulo. */
  width: number;
};

/** Linha da cronologia reconstruída, com a fonte que a originou. */
export type ChronologyEntry = {
  hour: string;
  source: string;
  description: string;
  /** Marca os instantes que sustentam a hipótese líder. */
  accent?: boolean;
};

export const timeAxis = ["19:30", "19:45", "20:00", "20:15", "20:30"];

export const timelineRows: TimelineRow[] = [
  { label: "Deploy", source: "Tsuru", event: "build 2026.3.0", detail: "19:58 · globoplay-tv", kind: "deploy", start: 57, width: 1.4 },
  { label: "Player QoE", source: "Youbora/NPAW", event: "falha de play 18,4%", detail: "start error · webOS 3.x", kind: "critical", start: 63, width: 35 },
  { label: "CDN", source: "Prometheus VTS", event: "p95 +12%", detail: "PoP Fortaleza", kind: "neutral", start: 59, width: 13 },
  { label: "Backend", source: "NewRelic APM", event: "autoscale +4 pods", detail: "apdex estável", kind: "neutral", start: 61, width: 8 },
  { label: "Identidade", source: "Apollo", event: "p99 auth 980 ms", detail: "efeito de retentativa", kind: "neutral", start: 68, width: 11 },
  { label: "Incidentes", source: "ServiceNow", event: "nenhum chamado", detail: "detecção 7 min antes", kind: "empty", start: 91, width: 0 },
];

export const chronology: ChronologyEntry[] = [
  { hour: "19:58", source: "TSURU", accent: true, description: "Deploy do build 2026.3.0 para a superfície TV. Rollout progressivo, 100% em 4 min." },
  { hour: "20:00", source: "NEWRELIC", description: "Autoscale sobe 4 pods no backend de playback. Apdex permanece em 0,94." },
  { hour: "20:02", source: "PROMETHEUS", description: "p95 na borda do PoP Fortaleza sobe de 368 ms para 412 ms." },
  { hour: "20:04", source: "YOUBORA", accent: true, description: "Primeira falha de início de play em LG webOS 3.x no Nordeste. dash_shaka_playback:6_6002." },
  { hour: "20:06", source: "APOLLO", description: "p99 de Authorize sobe para 980 ms — compatível com retentativa do player." },
  { hour: "20:07", source: "AGENTE", accent: true, description: "Recorte fechado e hipótese 1 emitida com score 87. Nenhum chamado aberto até o momento." },
];

export const correlationWindow = {
  label: "20:00 → 20:11",
  description:
    "Intervalo em que o agente encontrou coincidência entre deploy, queda de QoE e ausência de sinal na CDN.",
  metrics: [
    { label: "Fontes com desvio", value: "3 de 13" },
    { label: "Eventos correlacionados", value: "412,9 k" },
    { label: "Detecção antes do 1º chamado", value: "7 min" },
    { label: "Hipótese líder", value: "87 / 100" },
  ],
};

/** Recorte analisado, exibido na barra de escopo. */
export const timelineScope = [
  { key: "plataforma", label: "plataforma", value: "webOS 3.x" },
  { key: "fabricante", label: "fabricante", value: "LG" },
  { key: "regiao", label: "região", value: "Nordeste" },
  { key: "app", label: "app", value: "2026.3.0" },
];

export const scopeSummary = "41.209 sessões · 3,1% do tráfego · 6 fontes cruzadas";
