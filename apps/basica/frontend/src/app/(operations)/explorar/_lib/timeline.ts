import { timeline } from "../_mocks/scenario";

export const periodPresets = [
  { label: "15 min", minutes: 15 },
  { label: "30 min", minutes: 30 },
  { label: "3 h", minutes: 180 },
  { label: "24 h", minutes: 1_440 },
] as const;

const historyMinutes = 1_440;
export const historyStepMinutes = 5;
const historyPointCount = historyMinutes / historyStepMinutes + 1;
export const historyLastIndex = historyPointCount - 1;
export const minimumRangeSteps = 15 / historyStepMinutes;
export const defaultRangeSteps = 30 / historyStepMinutes;
const mockEndMinute = 20 * 60 + 11;

export const historyTimeline = createHistoryTimeline();
export const previewMaximum = Math.max(
  ...timeline.map((point) => point.events + point.errors),
);

function createHistoryTimeline() {
  return Array.from({ length: historyPointCount }, (_, index) => {
    const sourcePosition =
      (index / historyLastIndex) * Math.max(0, timeline.length - 1);
    const sourceStart = Math.floor(sourcePosition);
    const sourceEnd = Math.min(timeline.length - 1, sourceStart + 1);
    const progress = sourcePosition - sourceStart;
    const start = timeline[sourceStart];
    const end = timeline[sourceEnd];
    const variation = 1 + Math.sin(index * 1.7) * 0.035;

    return {
      errors: Math.max(
        1,
        Math.round(
          (start.errors + (end.errors - start.errors) * progress) * variation,
        ),
      ),
      events: Math.max(
        8,
        Math.round(
          (start.events + (end.events - start.events) * progress) * variation,
        ),
      ),
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

export function formatTimelinePoint(index: number, includeDay = false): string {
  const absoluteMinute =
    mockEndMinute - historyMinutes + index * historyStepMinutes;
  const isYesterday = absoluteMinute < 0;
  const minuteOfDay = ((absoluteMinute % 1_440) + 1_440) % 1_440;
  const hours = Math.floor(minuteOfDay / 60).toString().padStart(2, "0");
  const minutes = (minuteOfDay % 60).toString().padStart(2, "0");
  const day = isYesterday ? "ontem" : "hoje";

  return `${includeDay || isYesterday ? `${day} · ` : ""}${hours}:${minutes}`;
}

export function createAxisLabels(start: number, end: number) {
  const tickCount = Math.min(5, end - start + 1);

  return Array.from({ length: tickCount }, (_, index) => {
    const pointIndex = Math.round(
      start + ((end - start) * index) / Math.max(1, tickCount - 1),
    );

    return {
      index: pointIndex,
      label: formatTimelinePoint(pointIndex),
    };
  }).filter(
    (item, index, items) =>
      index === 0 || item.index !== items[index - 1]?.index,
  );
}
