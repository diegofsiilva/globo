import type { ApiEvent } from "@/lib/events/api";
import {
  formatDuration,
  needsAttention,
  shorten,
} from "@/lib/events/monitor";

type EventRowProps = {
  event: ApiEvent;
  onSelect: () => void;
  selected: boolean;
};

/** Linha reutilizável para listas selecionáveis de eventos. */
export function EventRow({ event, onSelect, selected }: EventRowProps) {
  const attention = needsAttention(event);
  const context = [event.device_manufacturer, event.device_model, event.route_path]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      className={`signal-row ${selected ? "selected" : ""}`}
      type="button"
      onClick={onSelect}
    >
      <span className="signal-name">
        <i className={attention ? "attention" : ""} />
        <b>
          {event.event_name}
          {event.action ? ` · ${event.action}` : ""}
        </b>
      </span>
      <span>{context || "não informado"}</span>
      <strong>{new Date(event.occurred_at).toLocaleTimeString("pt-BR")}</strong>
      <span>{formatDuration(event)}</span>
      <b className={attention ? "critical" : "muted"}>
        {attention ? "atenção" : "normal"}
      </b>
      <span>{event.app_version ?? "—"}</span>
      <strong title={event.session_id}>{shorten(event.session_id)}</strong>
    </button>
  );
}
