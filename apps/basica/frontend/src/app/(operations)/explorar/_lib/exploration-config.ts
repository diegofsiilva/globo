import type { GroupBy } from "./types";

export const groupOptions: GroupBy[] = [
  "Dispositivo",
  "Fonte",
  "Métrica",
  "Hora",
  "Dia da semana",
];

/** Dimensão real (`GET /api/v1/series/breakdown?dimension=`) por opção da UI.
 *
 * São as dimensões de `gold.v_feature_bucket`: a série é indexada por
 * (fonte, entidade, métrica) e carrega hora BRT e dia da semana no próprio
 * bucket. "Dispositivo" é `entity` restrita à fonte `youbora_device`, que
 * tem 2.897 aparelhos reais -- o recorte por fonte é aplicado pelo escopo.
 */
export const groupByDimension: Record<GroupBy, string> = {
  Dispositivo: "entity",
  Fonte: "source",
  Métrica: "metric",
  Hora: "hora_brt",
  "Dia da semana": "dow",
};

/** Escopo extra que cada agrupamento exige para o número fazer sentido.
 *
 * Sem prender "Dispositivo" à fonte de dispositivo, o mesmo eixo `entity`
 * misturaria aparelho, pod do Prometheus e vhost do rpaas na mesma tabela.
 */
export const groupByScope: Partial<Record<GroupBy, Record<string, string>>> = {
  Dispositivo: { source: "youbora_device" },
};

export function formatEvents(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}
