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
  metric: string;
  scope: string;
  sessions: string;
  severity: SignalSeverity;
  source: string;
  title: string;
  trend: number[];
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
