/**
 * Recorte estático inspirado no snapshot Argus de 06/08/2026.
 *
 * Os nomes de tabelas, métricas e dimensões seguem DATASET.md e db_schema.sql
 * do dataset_globo. Os valores foram arredondados e combinados para prototipar
 * a experiência sem carregar o dump MySQL no frontend.
 */

export type SignalSeverity = "critical" | "warning" | "stable";

export type SignalDeviation = {
  baseline: string;
  current: string;
  delta: string;
  id: string;
  threshold: string;
  detectedAt: string;
  lastObservedAt: string;
  interpretation: string;
  relatedPaths: { timeline: string; cut: string; hypotheses?: string };
  metric: string;
  scope: string;
  sessions: string;
  severity: SignalSeverity;
  source: string;
  title: string;
  trend: number[];
  /** Desvio em desvios-padrão, que é a chave de ordenação da lista. */
  zScore?: string;
};

export type OpenDegradation = {
  description: string;
  id: string;
  openedAt: string;
  scope: string;
  severity: "alto" | "atenção";
  source: string;
  title: string;
};

export const agoraFilters = {
  apps: ["2026.3.0", "2026.2.8", "2026.2.4"],
  manufacturers: ["LG", "Samsung", "Roku"],
  platforms: ["webOS 3.x", "Tizen 3.0", "Android TV", "Roku OS"],
  regions: ["Nordeste", "Sudeste", "Sul", "Centro-Oeste"],
};

export const activeDegradation = {
  baselineMultiplier: "×15",
  detectedAt: "20:04",
  failureRate: "18,4%",
  impactedSessions: "41.209",
  openFor: "7 min",
  title: "Play não inicia em TVs LG\nwebOS 3.x no Nordeste",
};

export const signalDeviations: SignalDeviation[] = [
  {
    baseline: "1,2%",
    current: "18,4%",
    delta: "+17,2 pp",
    id: "startup-errors-lg",
    threshold: "acima de 4,0% por 3 buckets consecutivos",
    detectedAt: "20:04:12",
    lastObservedAt: "20:11:06",
    interpretation: "A falha ocorre antes do primeiro frame e está concentrada no app 2026.3.0 em webOS 3.x.",
    relatedPaths: { timeline: "/timeline?sinal=startup-errors-lg", cut: "/recorte?sinal=startup-errors-lg" },
    metric: "errors + startup_errors / sessions",
    scope: "LG · webOS 3.x · NE",
    sessions: "41.209",
    severity: "critical",
    source: "device_hourly + live_qoe_hourly",
    title: "Falha antes do primeiro frame",
    trend: [2, 3, 2, 4, 3, 5, 4, 5, 4, 6, 5, 5, 7, 9, 12, 16, 20, 24, 28, 31],
  },
  {
    baseline: "2.140",
    current: "38.774",
    delta: "×18,1",
    id: "dash-shaka-errors",
    threshold: "acima de 5.000 erros por janela",
    detectedAt: "20:04:19",
    lastObservedAt: "20:11:02",
    interpretation: "O erro de playback acompanha a mesma população da falha de início e reforça a hipótese de regressão no player.",
    relatedPaths: { timeline: "/timeline?sinal=dash-shaka-errors", cut: "/recorte?sinal=dash-shaka-errors" },
    metric: "category=player · dash_shaka_playback",
    scope: "live · DRM off",
    sessions: "29.880",
    severity: "critical",
    source: "error_cat_hourly",
    title: "Erro dash_shaka_playback",
    trend: [5, 4, 6, 5, 5, 7, 6, 8, 7, 8, 6, 7, 12, 15, 18, 23, 26, 29, 31, 34],
  },
  {
    baseline: "2,6",
    current: "4,1",
    delta: "+1,5",
    id: "player-stalls",
    threshold: "acima de 3,5 travadas por sessão",
    detectedAt: "19:58:31",
    lastObservedAt: "20:10:55",
    interpretation: "O aumento é moderado e afeta Android TV; não pertence ao núcleo crítico em LG webOS.",
    relatedPaths: { timeline: "/timeline?sinal=player-stalls", cut: "/recorte?sinal=player-stalls" },
    metric: "stalls_avg",
    scope: "Android TV · live",
    sessions: "12.400",
    severity: "warning",
    source: "player_live_hourly",
    title: "Travadas por sessão",
    trend: [3, 4, 3, 4, 5, 4, 4, 5, 4, 5, 5, 4, 6, 7, 6, 9, 8, 12, 14, 16],
  },
  {
    baseline: "368 ms",
    current: "412 ms",
    delta: "+12%",
    id: "edge-p95",
    threshold: "acima de 400 ms por 5 minutos",
    detectedAt: "19:52:08",
    lastObservedAt: "20:10:48",
    interpretation: "A borda está acima do envelope semanal, mas o impacto não explica sozinha a concentração por dispositivo.",
    relatedPaths: { timeline: "/timeline?sinal=edge-p95", cut: "/recorte?sinal=edge-p95" },
    metric: "p95_ms",
    scope: "br1|playback.video.globo.com",
    sessions: "188.900",
    severity: "warning",
    source: "rpaas_bucket",
    title: "Latência p95 da borda",
    trend: [8, 9, 8, 10, 9, 11, 10, 9, 11, 12, 11, 12, 13, 12, 13, 14, 13, 14, 14, 13],
  },
  {
    baseline: "3,8 s",
    current: "3,9 s",
    delta: "+2%",
    id: "join-time",
    threshold: "acima de 4,2 s",
    detectedAt: "sem alerta",
    lastObservedAt: "20:10:42",
    interpretation: "A variação permanece dentro do envelope esperado e funciona como sinal de controle.",
    relatedPaths: { timeline: "/timeline?sinal=join-time", cut: "/recorte?sinal=join-time" },
    metric: "jointime_s_avg",
    scope: "todos os sinais live",
    sessions: "402.110",
    severity: "stable",
    source: "live_qoe_hourly",
    title: "Tempo para iniciar o vídeo",
    trend: [7, 6, 7, 6, 8, 7, 6, 7, 8, 7, 6, 8, 7, 8, 7, 8, 7, 8, 8, 7],
  },
  {
    baseline: "2,1%",
    current: "2,2%",
    delta: "+4%",
    id: "active-errors",
    threshold: "acima de 3,0%",
    detectedAt: "sem alerta",
    lastObservedAt: "20:10:36",
    interpretation: "A taxa agregada dilui a concentração observada no recorte LG webOS e não indica degradação global.",
    relatedPaths: { timeline: "/timeline?sinal=active-errors", cut: "/recorte?sinal=active-errors" },
    metric: "active_with_error / active_sessions",
    scope: "globo-rj · globo-sp · globo-bh",
    sessions: "96.500",
    severity: "stable",
    source: "live_active_15min",
    title: "Sessões concorrentes com erro",
    trend: [5, 5, 6, 5, 5, 6, 5, 6, 5, 5, 6, 6, 5, 6, 6, 5, 6, 6, 6, 6],
  },
];

export const openDegradations: OpenDegradation[] = [
  {
    description: "Falhas de início corroboradas por QoE e erros de dispositivo.",
    id: "deg-lg-webos",
    openedAt: "19:41",
    scope: "LG · webOS · Nordeste",
    severity: "alto",
    source: "device_hourly + live_qoe_hourly",
    title: "Falha de play em TVs LG após versão 2026.3.0",
  },
  {
    description: "Latência 12% acima do baseline semanal no endpoint de playback.",
    id: "deg-edge-p95",
    openedAt: "19:52",
    scope: "RPAAS · região br1",
    severity: "atenção",
    source: "rpaas_bucket",
    title: "p95 da borda acima do envelope esperado",
  },
  {
    description: "Concentração por UF × operadora sugere impacto de last-mile.",
    id: "deg-isp-rj",
    openedAt: "20:01",
    scope: "RJ · operadora agregada",
    severity: "atenção",
    source: "geo_hourly",
    title: "Taxa de erro concentrada em uma operadora",
  },
];
