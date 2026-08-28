import type { TimeseriesBucket } from "./api";

export const periodPresets = [
  { label: "15 min", minutes: 15 },
  { label: "30 min", minutes: 30 },
  { label: "3 h", minutes: 180 },
  { label: "24 h", minutes: 1_440 },
] as const;

export const historyMinutes = 1_440;
export const historyStepMinutes = 5;
const historyPointCount = historyMinutes / historyStepMinutes + 1;
export const historyLastIndex = historyPointCount - 1;
export const minimumRangeSteps = 15 / historyStepMinutes;
export const defaultRangeSteps = 30 / historyStepMinutes;

export type DensePoint = {
  total: number;
  byEventName: Record<string, number>;
  bucketTs: string;
};

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

export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes ? `${hours} h ${remainingMinutes} min` : `${hours} h`;
}

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
