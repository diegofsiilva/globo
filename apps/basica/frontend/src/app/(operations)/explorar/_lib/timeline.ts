import type { TimeseriesBucket } from "./api";

/** Períodos oferecidos no seletor da tela, do mais curto ao mais longo. */
export const periodPresets = [
  { label: "15 min", minutes: 15 },
  { label: "30 min", minutes: 30 },
  { label: "3 h", minutes: 180 },
  { label: "24 h", minutes: 1_440 },
] as const;

/**
 * Quanto tempo a faixa navegável cobre: 24 horas.
 *
 * A tela carrega a janela inteira uma vez e deixa a pessoa arrastar o recorte
 * dentro dela. Recarregar a cada arraste faria uma consulta por movimento do
 * mouse.
 */
export const historyMinutes = 1_440;
/**
 * Resolução da faixa: um ponto a cada 5 minutos, 289 no total.
 *
 * Mais fino não acrescenta leitura — a faixa não tem 1.440 pixels de largura —
 * e multiplicaria o payload.
 */
export const historyStepMinutes = 5;
const historyPointCount = historyMinutes / historyStepMinutes + 1;
/** Índice do último ponto da faixa, que corresponde a `now`. */
export const historyLastIndex = historyPointCount - 1;
/** Recorte mínimo arrastável: 15 minutos. Abaixo disso o gráfico fica ilegível. */
export const minimumRangeSteps = 15 / historyStepMinutes;
/** Recorte inicial ao abrir a tela: os últimos 30 minutos. */
export const defaultRangeSteps = 30 / historyStepMinutes;

/** Um ponto da série densa, com o total e a quebra por métrica. */
export type DensePoint = {
  total: number;
  byEventName: Record<string, number>;
  bucketTs: string;
};

/** Um ponto já reduzido às duas medidas que o gráfico desenha. */
export type ChartPoint = { events: number; errors: number; bucketTs: string };

/**
 * Converte os buckets esparsos vindos da API (só existem intervalos com
 * evento) em uma série densa de `historyPointCount` posições, alinhada ao
 * fim em `now`. Índices sem bucket correspondente na API viram zero -- é a
 * mesma leitura que o gráfico já fazia implicitamente com o mock denso.
 */
export function buildDenseTimeline(
  buckets: TimeseriesBucket[],
  now: Date,
): DensePoint[] {
  const byBucketStart = new Map<number, TimeseriesBucket>();
  for (const bucket of buckets) {
    byBucketStart.set(new Date(bucket.bucket).getTime(), bucket);
  }

  const endMs = now.getTime();
  const stepMs = historyStepMinutes * 60_000;

  return Array.from({ length: historyPointCount }, (_, index) => {
    const targetMs = endMs - (historyLastIndex - index) * stepMs;
    const bucketMs = Math.floor(targetMs / stepMs) * stepMs;
    const bucket = byBucketStart.get(bucketMs);

    return {
      total: bucket?.count ?? 0,
      byEventName: bucket?.by_event_name ?? {},
      bucketTs: new Date(bucketMs).toISOString(),
    };
  });
}

/**
 * Reduz a série a no máximo `maximumBars` barras, tirando a MÉDIA de cada grupo.
 *
 * Média, e não amostragem: a faixa de 24 h tem 289 pontos e o gráfico cabe em
 * algumas dezenas de barras. Amostrar mostraria o valor de um ponto arbitrário e
 * esconderia picos entre eles; a média preserva a magnitude do que aconteceu no
 * intervalo.
 *
 * @param points Pontos ordenados por tempo.
 * @param maximumBars Quantas barras o gráfico comporta.
 * @returns A série reduzida, ou a original quando já cabe.
 */
export function condenseTimeline<T extends { errors: number; events: number }>(
  points: T[],
  maximumBars = 56,
) {
  if (points.length <= maximumBars) return points;

  const bucketSize = Math.ceil(points.length / maximumBars);

  return Array.from(
    { length: Math.ceil(points.length / bucketSize) },
    (_, bucketIndex) => {
      const bucket = points.slice(
        bucketIndex * bucketSize,
        (bucketIndex + 1) * bucketSize,
      );

      return {
        errors: Math.round(
          bucket.reduce((total, point) => total + point.errors, 0) /
            bucket.length,
        ),
        events: Math.round(
          bucket.reduce((total, point) => total + point.events, 0) /
            bucket.length,
        ),
      };
    },
  );
}

/**
 * Formata uma duração em minutos para leitura ("45 min", "2 h 15 min").
 *
 * @param minutes Duração em minutos.
 * @returns O texto formatado, sem a parte de minutos quando ela é zero.
 */
export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes ? `${hours} h ${remainingMinutes} min` : `${hours} h`;
}

/**
 * Formata o instante de um ponto da faixa.
 *
 * O prefixo "ontem" aparece sozinho quando o ponto cai no dia anterior — numa
 * faixa de 24 h, "23:40" sem qualificação é ambíguo entre dois dias.
 *
 * @param bucketTs Instante do ponto, em ISO 8601.
 * @param now Instante de referência. É o relógio VIRTUAL, não `new Date()`.
 * @param includeDay Força o prefixo do dia mesmo quando o ponto é de hoje.
 * @returns O rótulo do ponto.
 */
export function formatTimelinePoint(
  bucketTs: string,
  now: Date,
  includeDay = false,
): string {
  const date = new Date(bucketTs);
  const isYesterday = date.toDateString() !== now.toDateString();
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");
  const day = isYesterday ? "ontem" : "hoje";

  return `${includeDay || isYesterday ? `${day} · ` : ""}${hours}:${minutes}`;
}

/**
 * Monta até cinco marcações para o eixo do tempo, distribuídas no recorte.
 *
 * O filtro final remove índices repetidos: num recorte curto, duas marcações
 * podem cair no mesmo ponto, e o eixo mostraria o mesmo horário duas vezes.
 *
 * @param points Pontos da faixa completa.
 * @param start Índice inicial do recorte visível.
 * @param end Índice final do recorte visível.
 * @param now Instante de referência, do relógio virtual.
 * @returns Índice e rótulo de cada marcação.
 */
export function createAxisLabels(points: { bucketTs: string }[], start: number, end: number, now: Date) {
  const tickCount = Math.min(5, end - start + 1);

  return Array.from({ length: tickCount }, (_, index) => {
    const pointIndex = Math.round(
      start + ((end - start) * index) / Math.max(1, tickCount - 1),
    );
    const point = points[pointIndex];

    return {
      index: pointIndex,
      label: point ? formatTimelinePoint(point.bucketTs, now) : "--:--",
    };
  }).filter(
    (item, index, items) =>
      index === 0 || item.index !== items[index - 1]?.index,
  );
}
