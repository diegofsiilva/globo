import type { GroupBy } from "./types";

export const groupOptions: GroupBy[] = ["Modelo", "UF", "ISP", "Versão", "Rota"];

/** Dimensão real (`GET /api/v1/metrics/breakdown?dimension=`) por opção de agrupamento da UI. */
export const groupByDimension: Record<GroupBy, string> = {
  Modelo: "device_model",
  UF: "uf",
  ISP: "isp",
  Versão: "app_version",
  Rota: "route_path",
};

/** Campos de filtro cumulativo exibidos como chips de escopo, com o `field` real usado em `/api/v1/facets`. */
export const scopeFilterDefs = [
  { id: "platform", label: "plataforma", field: "device_os" },
  { id: "manufacturer", label: "fabricante", field: "device_manufacturer" },
  { id: "region", label: "região", field: "uf" },
  { id: "app", label: "app", field: "app_version" },
] as const;

export function formatEvents(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}
