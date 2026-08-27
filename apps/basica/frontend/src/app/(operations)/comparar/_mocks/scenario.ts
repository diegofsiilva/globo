/** Cenário fixo da tela 03 — Comparar (artefatos/entendimento_ux.md §5.3.3).
 *
 * As quatro referências existem porque sazonalidade tem escalas diferentes: o
 * mesmo horário de ontem, a mesma faixa da semana passada, a última janela sem
 * desvio e o pico ao vivo anterior. Num evento programado o comportamento
 * correto é comparar contra outro pico, não contra a média.
 */

/** Referência histórica contra a qual a janela atual é comparada. */
export type ComparisonReference = {
  id: ReferenceId;
  label: string;
  /** Data e faixa da janela de referência. */
  detail: string;
  /** Cabeçalho da coluna na tabela de métricas. */
  column: string;
};

export type ReferenceId = "ontem" | "semana" | "estavel" | "pico";

/** Leitura de uma métrica contra uma referência. */
export type MetricComparison = {
  /** Valor na referência, já formatado. */
  value: string;
  /** Variação em relação a agora, já formatada. */
  delta: string;
  /** Distância do esperado, em desvios-padrão. */
  sigma: number;
};

/** Linha da tabela: uma métrica medida agora e contra cada referência. */
export type ComparedMetric = {
  label: string;
  /** Valor na janela atual, já formatado. */
  now: string;
  references: Record<ReferenceId, MetricComparison>;
};

/** Evento de infraestrutura ocorrido entre as duas janelas. */
export type WindowChange = {
  hour: string;
  description: string;
};

export const references: ComparisonReference[] = [
  { id: "ontem", label: "Ontem, mesmo horário", detail: "13/07 · 20:11", column: "ontem" },
  { id: "semana", label: "Semana passada", detail: "06/07 · 20:11", column: "semana passada" },
  { id: "estavel", label: "Última janela estável", detail: "hoje · 19:00–19:45", column: "janela estável" },
  { id: "pico", label: "Pico ao vivo anterior", detail: "12/07 · final BRA×ARG", column: "pico anterior" },
];

/* A significância é o que hierarquiza: falha de play a 14,2σ e p95 de borda a
   1,2σ sobem juntos em porcentagem, mas só o primeiro está fora da variação
   normal da métrica. */
export const metrics: ComparedMetric[] = [
  {
    label: "Falha de início de play",
    now: "18,4%",
    references: {
      ontem: { value: "1,4%", delta: "+17,0 pp", sigma: 13.6 },
      semana: { value: "1,2%", delta: "+17,2 pp", sigma: 14.2 },
      estavel: { value: "1,1%", delta: "+17,3 pp", sigma: 15.1 },
      pico: { value: "1,9%", delta: "+16,5 pp", sigma: 11.8 },
    },
  },
  {
    label: "Join time médio",
    now: "9,4 s",
    references: {
      ontem: { value: "3,3 s", delta: "+185%", sigma: 8.1 },
      semana: { value: "3,1 s", delta: "+203%", sigma: 8.9 },
      estavel: { value: "3,0 s", delta: "+213%", sigma: 9.4 },
      pico: { value: "3,8 s", delta: "+147%", sigma: 6.7 },
    },
  },
  {
    label: "Buffer ratio",
    now: "4,8%",
    references: {
      ontem: { value: "1,2%", delta: "+3,6 pp", sigma: 6.0 },
      semana: { value: "1,1%", delta: "+3,7 pp", sigma: 6.4 },
      estavel: { value: "1,0%", delta: "+3,8 pp", sigma: 6.9 },
      pico: { value: "1,6%", delta: "+3,2 pp", sigma: 4.8 },
    },
  },
  {
    label: "Sessões ativas",
    now: "41.209",
    references: {
      ontem: { value: "44.100", delta: "−7%", sigma: 1.4 },
      semana: { value: "46.880", delta: "−12%", sigma: 2.1 },
      estavel: { value: "39.700", delta: "+4%", sigma: 0.6 },
      pico: { value: "118.400", delta: "−65%", sigma: 7.3 },
    },
  },
  {
    label: "p95 de borda (RPaaS)",
    now: "412 ms",
    references: {
      ontem: { value: "372 ms", delta: "+11%", sigma: 1.1 },
      semana: { value: "368 ms", delta: "+12%", sigma: 1.2 },
      estavel: { value: "361 ms", delta: "+14%", sigma: 1.5 },
      pico: { value: "445 ms", delta: "−7%", sigma: 0.8 },
    },
  },
  {
    label: "Erro de autorização",
    now: "0,4%",
    references: {
      ontem: { value: "0,4%", delta: "0%", sigma: 0.1 },
      semana: { value: "0,4%", delta: "0%", sigma: 0.2 },
      estavel: { value: "0,3%", delta: "+0,1 pp", sigma: 0.4 },
      pico: { value: "0,6%", delta: "−0,2 pp", sigma: 0.7 },
    },
  },
  {
    label: "Bitrate médio",
    now: "2,8 Mbps",
    references: {
      ontem: { value: "2,9 Mbps", delta: "−3%", sigma: 0.4 },
      semana: { value: "2,9 Mbps", delta: "−3%", sigma: 0.5 },
      estavel: { value: "2,9 Mbps", delta: "−3%", sigma: 0.5 },
      pico: { value: "2,7 Mbps", delta: "+4%", sigma: 0.6 },
    },
  },
];

/** Bucket de 1 min da métrica em destaque, agora e na referência. */
export type ChartBucket = {
  /** Minuto do bucket, no formato HH:MM. */
  hour: string;
  /** Falha de início de play na janela atual, em %. */
  now: number;
  /** Mesma métrica na referência selecionada, em %. */
  reference: number;
  /** Marca o bucket que saiu do envelope histórico. */
  outside?: boolean;
};

/** Série de 19:41 a 20:11 — a janela do seletor de período, bucket de 1 min. */
export const chart: ChartBucket[] = [
  { hour: "19:41", now: 1.2, reference: 1.2 },
  { hour: "19:42", now: 1.1, reference: 1.3 },
  { hour: "19:43", now: 1.3, reference: 1.2 },
  { hour: "19:44", now: 1.2, reference: 1.1 },
  { hour: "19:45", now: 1.4, reference: 1.3 },
  { hour: "19:46", now: 1.3, reference: 1.2 },
  { hour: "19:47", now: 1.2, reference: 1.2 },
  { hour: "19:48", now: 1.1, reference: 1.3 },
  { hour: "19:49", now: 1.2, reference: 1.2 },
  { hour: "19:50", now: 1.3, reference: 1.1 },
  { hour: "19:51", now: 1.1, reference: 1.2 },
  { hour: "19:52", now: 1.0, reference: 1.2 },
  { hour: "19:53", now: 1.2, reference: 1.3 },
  { hour: "19:54", now: 1.3, reference: 1.2 },
  { hour: "19:55", now: 1.2, reference: 1.1 },
  { hour: "19:56", now: 1.1, reference: 1.2 },
  { hour: "19:57", now: 1.3, reference: 1.2 },
  { hour: "19:58", now: 1.2, reference: 1.3 },
  { hour: "19:59", now: 1.4, reference: 1.2 },
  { hour: "20:00", now: 2.4, reference: 1.2, outside: true },
  { hour: "20:01", now: 3.1, reference: 1.1, outside: true },
  { hour: "20:02", now: 3.4, reference: 1.2, outside: true },
  { hour: "20:03", now: 5.9, reference: 1.3, outside: true },
  { hour: "20:04", now: 7.2, reference: 1.2, outside: true },
  { hour: "20:05", now: 8.8, reference: 1.2, outside: true },
  { hour: "20:06", now: 10.1, reference: 1.1, outside: true },
  { hour: "20:07", now: 11.6, reference: 1.2, outside: true },
  { hour: "20:08", now: 13.2, reference: 1.3, outside: true },
  { hour: "20:09", now: 14.8, reference: 1.2, outside: true },
  { hour: "20:10", now: 16.6, reference: 1.2, outside: true },
  { hour: "20:11", now: 18.4, reference: 1.3, outside: true },
];

export const changes: WindowChange[] = [
  { hour: "19:58", description: "Deploy globoplay-tv 2026.3.0 (Tsuru)" },
  { hour: "20:00", description: "Autoscale +4 pods no backend de playback" },
  { hour: "20:02", description: "p95 de borda sobe 12% no PoP Fortaleza" },
  { hour: "20:04", description: "Primeira falha de play no recorte" },
];

/** Recorte analisado, exibido na barra de escopo. */
export const compareScope = [
  { key: "plataforma", label: "plataforma", value: "webOS 3.x" },
  { key: "fabricante", label: "fabricante", value: "LG" },
  { key: "regiao", label: "região", value: "Nordeste" },
  { key: "app", label: "app", value: "2026.3.0" },
];

export const scopeSummary = "41.209 sessões · 3,1% do tráfego · 6 fontes cruzadas";
