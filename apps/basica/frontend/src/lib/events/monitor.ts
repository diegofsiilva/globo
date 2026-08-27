import type { ApiEvent, EventQuery } from "./api";

export type Period = "15" | "30" | "180" | "1440" | "all";
export type EventStatus = "all" | "attention" | "normal";

export type MonitorFilters = {
  eventType: string;
  manufacturer: string;
  platform: string;
  search: string;
  status: EventStatus;
};

export const PERIODS: Period[] = ["15", "30", "180", "1440", "all"];

/** Filtra e ordena os eventos exibidos no dashboard. */
export function filterEvents(events: ApiEvent[], filters: MonitorFilters) {
  const normalizedSearch = filters.search.trim().toLocaleLowerCase("pt-BR");

  return events
    .filter((event) => {
      const haystack = [
        event.event_id,
        event.event_name,
        event.action,
        event.device_manufacturer,
        event.device_model,
        event.device_os,
        event.device_os_version,
        event.app_version,
        event.route_path,
        event.session_id,
      ]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase("pt-BR");

      return (
        (filters.platform === "all" || platformName(event) === filters.platform) &&
        (filters.manufacturer === "all" ||
          event.device_manufacturer === filters.manufacturer) &&
        (filters.eventType === "all" || event.event_name === filters.eventType) &&
        (filters.status === "all" ||
          (filters.status === "attention") === needsAttention(event)) &&
        haystack.includes(normalizedSearch)
      );
    })
    .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at));
}

export function needsAttention(event: ApiEvent) {
  return (
    event.event_name === "error" ||
    (event.event_name === "vitals" && event.action === "frozen")
  );
}

export function platformName(event: ApiEvent) {
  return (
    [event.device_os, event.device_os_version]
      .filter((value) => value && value !== "unknown")
      .join(" ") || "não informada"
  );
}

export function formatDuration(event: ApiEvent) {
  return event.duration_ms == null
    ? "—"
    : `${event.duration_ms.toLocaleString("pt-BR")} ms`;
}

export function formatDate(value: string) {
  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

export function shorten(value: string) {
  return value.length > 12 ? `${value.slice(0, 10)}…` : value;
}

export function unique(values: string[]) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

export function isNonEmptyString(value: string | null): value is string {
  return Boolean(value);
}

export function isPeriod(value: string | null): value is Period {
  return PERIODS.some((period) => period === value);
}

export function periodLabel(period: Period) {
  if (period === "all") return "tudo";
  if (period === "180") return "3 h";
  if (period === "1440") return "24 h";
  return `${period} min`;
}

export function getPeriodQuery(period: Period): EventQuery {
  if (period === "all") return {};

  const to = new Date();

  return {
    from: new Date(to.getTime() - Number(period) * 60_000).toISOString(),
    to: to.toISOString(),
  };
}
