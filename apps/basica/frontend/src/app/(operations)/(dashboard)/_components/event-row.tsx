import type { ApiEvent } from "@/lib/events/api";
import clsx from "clsx";
import {
  formatDuration,
  needsAttention,
  shorten,
} from "@/lib/events/monitor";
import { dashboardStyles as styles } from "./dashboard.styles";

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
      className={clsx(styles.signalRow, selected && styles.selected)}
      type="button"
      onClick={onSelect}
    >
      <span className={styles.signalName}>
        <i className={clsx(attention && styles.attention)} />
        <b>
          {event.event_name}
          {event.action ? ` · ${event.action}` : ""}
        </b>
      </span>
      <span>{context || "não informado"}</span>
      <strong>{new Date(event.occurred_at).toLocaleTimeString("pt-BR")}</strong>
      <span>{formatDuration(event)}</span>
      <b className={clsx(attention ? styles.critical : styles.muted)}>
        {attention ? "atenção" : "normal"}
      </b>
      <span>{event.app_version ?? "—"}</span>
      <strong title={event.session_id}>{shorten(event.session_id)}</strong>
    </button>
  );
}
