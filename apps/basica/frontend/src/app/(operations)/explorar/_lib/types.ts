/** Um tipo de evento na barra de seleção, com a contagem já formatada. */
export type EventKind = {
  count: number;
  id: string;
  label: string;
  name: string;
  value: string;
};

/** Agrupamentos oferecidos pela tela.
 *
 * Trocados junto com a fonte de dados: "UF", "Versão" e "Rota" mapeavam
 * colunas de evento por sessao (`uf`, `app_version`, `route_path`) que este
 * dataset nao tem. Estes cinco mapeiam dimensoes reais de
 * `gold.v_feature_bucket` (ver `groupByDimension`).
 */
export type GroupBy = "Dispositivo" | "Fonte" | "Métrica" | "Hora" | "Dia da semana";

/**
 * Uma linha do agrupamento: o rótulo do grupo e as suas medidas.
 *
 * `delta` vem como texto, e não número, porque carrega o sinal e a unidade já
 * formatados para leitura direta na tabela.
 */
export type ExplorationRow = {
  delta: string;
  errorRate: number;
  events: number;
  label: string;
};

/** Um erro recorrente, com contagem e participação já formatadas. */
export type FrequentError = {
  count: string;
  id: string;
  name: string;
  share: string;
};
