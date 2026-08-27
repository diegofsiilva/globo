export type EventKind = {
  count: number;
  id: string;
  label: string;
  name: string;
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
