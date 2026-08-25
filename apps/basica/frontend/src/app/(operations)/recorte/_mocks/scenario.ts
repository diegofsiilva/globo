/** Cenário fixo da tela 06 — Recorte (artefatos/entendimento_ux.md §5.3.6).
 *
 * Portado da implementação de origem (branch docs/relatorio-front). Descreve a
 * mesma população do cenário de Hipóteses: 3,1% do tráfego concentrando 94%
 * dos erros da janela.
 */

/** Ajuste possível do recorte, com o efeito medido antes do clique. */
export type CutAdjustment = {
  title: string;
  /** Efeito sobre especificidade e cobertura. */
  result: string;
  /** Marca os ajustes que aumentam a especificidade. */
  critical?: boolean;
};

export const cutDefinition = {
  title: "LG · webOS 3.x · Nordeste · app 2026.3.0 · rota live",
  metrics: [
    { value: "41.209", label: "sessões" },
    { value: "3,1%", label: "do tráfego" },
    { value: "94%", label: "dos erros da janela" },
    { value: "9", label: "UFs" },
  ],
};

export const heatmapRegions = ["Norte", "Nordeste", "C.-Oeste", "Sudeste", "Sul"];

/** Taxa de erro por família de dispositivo × região, na ordem de `heatmapRegions`. */
export const heatmap: Array<{ family: string; rates: string[] }> = [
  { family: "LG webOS 3.x", rates: ["4,1%", "31,2%", "3,4%", "2,9%", "2,6%"] },
  { family: "LG webOS 4+", rates: ["1,4%", "2,1%", "1,2%", "1,1%", "1,0%"] },
  { family: "Samsung Tizen", rates: ["1,6%", "2,0%", "1,3%", "1,1%", "1,1%"] },
  { family: "Philco NetRange", rates: ["2,2%", "3,0%", "1,8%", "1,5%", "1,4%"] },
  { family: "Android TV", rates: ["1,8%", "2,4%", "1,5%", "1,4%", "1,3%"] },
  { family: "iOS / tvOS", rates: ["0,9%", "1,1%", "0,8%", "0,7%", "0,7%"] },
];

export const adjustments: CutAdjustment[] = [
  { title: "Restringir a ISP – Oi Fibra", result: "especificidade +12 · cobertura −38%", critical: true },
  { title: "Expandir para webOS 4.x", result: "especificidade −41 · dilui o sinal" },
  { title: "Restringir a rota – live", result: "especificidade +6 · cobertura −9%", critical: true },
  { title: "Remover recorte de região", result: "especificidade −23 · cobertura +64%" },
];

export const sampleColumns = ["Hora", "Modelo", "SO", "Evento", "Erro"];

export const samples: string[][] = [
  ["20:04:11", "49LJ5550-SC", "WebOS 3.9.0", "error", "dash_shaka_playback:6_6002"],
  ["20:04:44", "43LJ5500", "WebOS 3.8.0", "video_view", "start timeout · live"],
  ["20:05:19", "32LJ600B", "WebOS 3.4.0", "error", "media_source_not_supported"],
  ["20:05:52", "49LJ5550-SC", "WebOS 3.9.0", "vitals", "frozen · 0,78 s"],
  ["20:06:07", "43LJ5500", "WebOS 3.8.0", "error", "dash_shaka_playback:6_6002"],
  ["20:06:41", "55UJ6300", "WebOS 3.8.0", "video_view", "start timeout · live"],
];

/** Recorte analisado, exibido na barra de escopo. */
export const cutScope = [
  { key: "plataforma", label: "plataforma", value: "webOS 3.x" },
  { key: "fabricante", label: "fabricante", value: "LG" },
  { key: "regiao", label: "região", value: "Nordeste" },
  { key: "app", label: "app", value: "2026.3.0" },
];

export const scopeSummary = "41.209 sessões · 3,1% do tráfego · 6 fontes cruzadas";
