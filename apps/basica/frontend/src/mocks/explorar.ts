export type EventKind = {
  id: string;
  label: string;
  value: string;
};

export type GroupBy = "Modelo" | "UF" | "ISP" | "Versão" | "Rota";

export type ExplorationRow = {
  delta: string;
  errorRate: number;
  events: number;
  label: string;
};

export type FrequentError = {
  count: string;
  id: string;
  name: string;
  share: string;
};

export const eventKinds: EventKind[] = [
  { id: "request", label: "request", value: "42,8 M" },
  { id: "screen-view", label: "screen_view", value: "9,1 M" },
  { id: "video-view", label: "video_view", value: "6,4 M" },
  { id: "session", label: "session", value: "3,2 M" },
  { id: "vitals", label: "vitals", value: "1,8 M" },
  { id: "error", label: "error", value: "512 k" },
];

export const timeline = [
  { events: 45, errors: 3 },
  { events: 40, errors: 4 },
  { events: 35, errors: 2 },
  { events: 39, errors: 3 },
  { events: 37, errors: 4 },
  { events: 41, errors: 5 },
  { events: 43, errors: 3 },
  { events: 40, errors: 4 },
  { events: 48, errors: 4 },
  { events: 46, errors: 4 },
  { events: 44, errors: 5 },
  { events: 40, errors: 4 },
  { events: 45, errors: 6 },
  { events: 41, errors: 5 },
  { events: 38, errors: 4 },
  { events: 34, errors: 3 },
  { events: 43, errors: 7 },
  { events: 36, errors: 5 },
  { events: 52, errors: 4 },
  { events: 43, errors: 4 },
  { events: 41, errors: 5 },
  { events: 40, errors: 4 },
  { events: 44, errors: 4 },
  { events: 38, errors: 5 },
  { events: 49, errors: 5 },
  { events: 45, errors: 4 },
  { events: 47, errors: 6 },
  { events: 35, errors: 9 },
  { events: 51, errors: 14 },
  { events: 43, errors: 17 },
  { events: 39, errors: 21 },
  { events: 40, errors: 28 },
  { events: 41, errors: 34 },
  { events: 42, errors: 39 },
  { events: 46, errors: 42 },
  { events: 43, errors: 45 },
];

export const explorationGroups: Record<GroupBy, ExplorationRow[]> = {
  Modelo: [
    { label: "49LJ5550-SC", events: 112_408, errorRate: 31.2, delta: "+2.910%" },
    { label: "43LJ5500", events: 88_117, errorRate: 28.7, delta: "+2.410%" },
    { label: "32LJ600B", events: 41_902, errorRate: 24.1, delta: "+1.980%" },
    { label: "UN49MU6100", events: 96_330, errorRate: 2.1, delta: "+4%" },
    { label: "43D1200", events: 38_774, errorRate: 1.8, delta: "−2%" },
    { label: "50P65US", events: 31_220, errorRate: 1.6, delta: "+1%" },
    { label: "BTV32D10N5SKH", events: 22_804, errorRate: 1.4, delta: "0%" },
    { label: "UN43T5300", events: 18_902, errorRate: 1.1, delta: "−3%" },
  ],
  UF: [
    { label: "Bahia", events: 124_610, errorRate: 27.8, delta: "+2.540%" },
    { label: "Pernambuco", events: 98_402, errorRate: 24.2, delta: "+1.870%" },
    { label: "Ceará", events: 81_911, errorRate: 16.4, delta: "+940%" },
    { label: "Maranhão", events: 42_603, errorRate: 3.2, delta: "+9%" },
    { label: "Rio Grande do Norte", events: 38_552, errorRate: 2.4, delta: "+3%" },
    { label: "Paraíba", events: 31_985, errorRate: 1.8, delta: "−1%" },
  ],
  ISP: [
    { label: "Claro", events: 128_240, errorRate: 29.4, delta: "+2.660%" },
    { label: "Vivo", events: 102_118, errorRate: 21.6, delta: "+1.740%" },
    { label: "Oi", events: 74_823, errorRate: 17.9, delta: "+1.120%" },
    { label: "TIM", events: 48_291, errorRate: 4.8, delta: "+34%" },
    { label: "Brisanet", events: 21_602, errorRate: 2.1, delta: "+4%" },
  ],
  Versão: [
    { label: "2026.3.0", events: 302_118, errorRate: 26.9, delta: "+2.240%" },
    { label: "2026.2.8", events: 96_442, errorRate: 3.8, delta: "+18%" },
    { label: "2026.2.4", events: 44_908, errorRate: 2.2, delta: "+4%" },
    { label: "2026.1.9", events: 21_673, errorRate: 1.7, delta: "−2%" },
  ],
  Rota: [
    { label: "/playback/start", events: 148_320, errorRate: 30.2, delta: "+2.810%" },
    { label: "/video/live", events: 111_842, errorRate: 24.7, delta: "+1.930%" },
    { label: "/auth/token", events: 61_287, errorRate: 9.4, delta: "+280%" },
    { label: "/home", events: 56_109, errorRate: 2.5, delta: "+6%" },
    { label: "/search", events: 34_832, errorRate: 1.4, delta: "−1%" },
  ],
};

export const frequentErrors: FrequentError[] = [
  {
    id: "dash-shaka",
    name: "dash_shaka_playback:6_6002",
    count: "38.774",
    share: "78,1% do recorte",
  },
  {
    id: "media-source",
    name: "media_source_not_supported",
    count: "6.220",
    share: "12,5% do recorte",
  },
  {
    id: "manifest",
    name: "manifest_timeout",
    count: "2.914",
    share: "5,9% do recorte",
  },
  {
    id: "token",
    name: "auth_token_expired",
    count: "1.108",
    share: "2,2% do recorte",
  },
  {
    id: "geo",
    name: "arr_frozen_ui",
    count: "640",
    share: "1,3% do recorte",
  },
];
