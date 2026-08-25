import type { GroupBy } from "../_mocks/scenario";

export const groupOptions: GroupBy[] = ["Modelo", "UF", "ISP", "Versão", "Rota"];

export const eventProfiles: Record<
  string,
  { errorHeight: number; eventHeight: number; rate: number }
> = {
  request: { errorHeight: 0.18, eventHeight: 1.08, rate: 0.18 },
  "screen-view": { errorHeight: 0.12, eventHeight: 0.9, rate: 0.12 },
  "video-view": { errorHeight: 0.48, eventHeight: 0.96, rate: 0.48 },
  session: { errorHeight: 0.24, eventHeight: 0.82, rate: 0.24 },
  vitals: { errorHeight: 0.1, eventHeight: 0.7, rate: 0.1 },
  error: { errorHeight: 1, eventHeight: 1, rate: 1 },
};

export const scopeFilters = [
  { id: "platform", label: "plataforma", value: "webOS 3.x" },
  { id: "manufacturer", label: "fabricante", value: "LG" },
  { id: "region", label: "região", value: "Nordeste" },
  { id: "app", label: "app", value: "2026.3.0" },
] as const;

export function formatEvents(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}
