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
