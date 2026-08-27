import type {
  HypothesesFilters,
  HypothesesReport,
  HypothesesSource,
} from "../_lib/types";
import { hypothesesScenario } from "./scenario";

/** Adapter determinístico usado quando a fonte mock é escolhida explicitamente. */
export const fetchHypothesesFromMock: HypothesesSource = async (filters = {}) =>
  mockReport(filters);

function mockReport(filters: HypothesesFilters): HypothesesReport {
  const from = filters.from ?? hypothesesScenario.window.from;
  const to = filters.to ?? hypothesesScenario.window.to;

  return {
    ...hypothesesScenario,
    window: { from, to, label: windowLabel(from, to) },
  };
}

function windowLabel(from: string, to: string): string {
  const time = (value: string) =>
    new Date(value).toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });

  return `${time(from)}–${time(to)}`;
}
