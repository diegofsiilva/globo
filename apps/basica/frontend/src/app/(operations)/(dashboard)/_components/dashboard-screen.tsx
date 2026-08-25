"use client";

/** Página raiz do dashboard de telemetria. */

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DetailField } from "./detail-field";
import { EventRow } from "./event-row";
import { FilterSelect } from "./filter-select";
import { Metric } from "./metric";
import { fetchEvents } from "@/lib/events/api";
import {
  PERIODS,
  filterEvents,
  formatDate,
  formatDuration,
  getPeriodQuery,
  isNonEmptyString,
  isPeriod,
  needsAttention,
  periodLabel,
  platformName,
  unique,
  type EventStatus,
  type Period,
} from "@/lib/events/monitor";
import styles from "../dashboard.module.css";

/** Renderiza e controla a página principal de monitoração. */
export function DashboardScreen() {
  const [period, setPeriod] = useState<Period>("30");
  const [now, setNow] = useState<Date | null>(null);
  const [platform, setPlatform] = useState("all");
  const [manufacturer, setManufacturer] = useState("all");
  const [eventType, setEventType] = useState("all");
  const [status, setStatus] = useState<EventStatus>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    const restoreTimer = window.setTimeout(() => {
      const savedPeriod = window.localStorage.getItem("event-monitor-period");

      if (isPeriod(savedPeriod)) setPeriod(savedPeriod);
      setNow(new Date());
    }, 0);
    const clockTimer = window.setInterval(() => setNow(new Date()), 1_000);

    return () => {
      window.clearTimeout(restoreTimer);
      window.clearInterval(clockTimer);
    };
  }, []);

  const eventsQuery = useQuery({
    queryKey: ["events", period],
    queryFn: ({ signal }) => fetchEvents(getPeriodQuery(period), signal),
    refetchInterval: 30_000,
  });

  const allEvents = useMemo(() => eventsQuery.data?.items ?? [], [eventsQuery.data]);
  const options = useMemo(
    () => ({
      eventTypes: unique(allEvents.map((event) => event.event_name)),
      manufacturers: unique(
        allEvents.map((event) => event.device_manufacturer).filter(isNonEmptyString),
      ),
      platforms: unique(allEvents.map(platformName)),
    }),
    [allEvents],
  );
  const filteredEvents = useMemo(
    () =>
      filterEvents(allEvents, {
        eventType,
        manufacturer,
        platform,
        search,
        status,
      }),
    [allEvents, eventType, manufacturer, platform, search, status],
  );

  const selectedEvent =
    filteredEvents.find((event) => event.event_id === selectedId) ??
    filteredEvents[0] ??
    null;
  const alertCount = filteredEvents.filter(needsAttention).length;
  const selectedDevice = selectedEvent
    ? [
        selectedEvent.device_manufacturer,
        selectedEvent.device_model,
        selectedEvent.device_model_year,
      ]
        .filter(Boolean)
        .join(" · ")
    : "";

  function selectPeriod(value: Period) {
    setPeriod(value);
    window.localStorage.setItem("event-monitor-period", value);
  }

  function clearFilters() {
    setPlatform("all");
    setManufacturer("all");
    setEventType("all");
    setStatus("all");
    setSearch("");
  }

  return (
    <div className={styles.dashboardShell}>
      <div
        className={styles.topControls}
        data-operations-slot="controls"
      >
        <div className={styles.live}>
          <i />
          {eventsQuery.isFetching ? "Atualizando" : "Ao vivo"} ·{" "}
          {now?.toLocaleTimeString("pt-BR") ?? "--:--:--"}
        </div>
        <div className={styles.periodPicker}>
          {PERIODS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={period === value}
              onClick={() => selectPeriod(value)}
            >
              {periodLabel(value)}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.scopeBar} data-operations-slot="scope">
        <span className={styles.scopeLabel}>Escopo</span>
        <FilterSelect
          label="plataforma"
          value={platform}
          onChange={setPlatform}
          options={options.platforms}
        />
        <FilterSelect
          label="fabricante"
          value={manufacturer}
          onChange={setManufacturer}
          options={options.manufacturers}
        />
        <FilterSelect
          label="evento"
          value={eventType}
          onChange={setEventType}
          options={options.eventTypes}
        />
        <FilterSelect
          label="status"
          value={status}
          onChange={(value) => setStatus(value as EventStatus)}
          options={["attention", "normal"]}
          labels={{ attention: "atenção", normal: "normal" }}
        />
        <input
          className={styles.eventSearch}
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="buscar evento…"
          aria-label="Buscar eventos"
        />
        <p>
          {filteredEvents.length} de {allEvents.length} eventos · {alertCount}{" "}
          requerem atenção
        </p>
        <button className={styles.clearFilter} type="button" onClick={clearFilters}>
          limpar
        </button>
      </div>

      <div className={styles.analysisArea} data-operations-slot="content">
          {selectedEvent ? (
            <section className={styles.incidentHero}>
              <p
                className={`${styles.incidentKicker} ${
                  needsAttention(selectedEvent) ? "" : styles.normal
                }`}
              >
                <i />
                {needsAttention(selectedEvent)
                  ? "Evento requer atenção"
                  : "Evento normal"}
                <span>{formatDate(selectedEvent.occurred_at)}</span>
              </p>
              <h1>
                {selectedEvent.event_name}
                {selectedEvent.action && (
                  <>
                    <br />
                    {selectedEvent.action}
                  </>
                )}
              </h1>
              <div className={styles.incidentStats}>
                <Metric
                  value={String(filteredEvents.length)}
                  label="eventos no recorte"
                />
                <Metric
                  value={selectedEvent.device_manufacturer ?? "—"}
                  label="fabricante"
                />
                <Metric value={platformName(selectedEvent)} label="plataforma" />
                <Metric value={formatDuration(selectedEvent)} label="duração" />
              </div>
            </section>
          ) : (
            <section className={`${styles.incidentHero} ${styles.emptyHero}`}>
              <p className={styles.incidentKicker}>Monitor de telemetria</p>
              <h1>Nenhum evento no recorte</h1>
              <p>Ajuste os filtros ou aguarde a próxima atualização.</p>
            </section>
          )}

          <section className={styles.signalsSection}>
            <header>
              <h2>Eventos coletados pela API</h2>
              <p>ordenados do mais recente para o mais antigo</p>
            </header>
            <div className={styles.signalTable}>
              <div className={styles.signalHead}>
                <span>evento</span>
                <span>dispositivo / rota</span>
                <span>horário</span>
                <span>duração</span>
                <span>status</span>
                <span>aplicativo</span>
                <span>sessão</span>
              </div>
              {filteredEvents.map((event) => (
                <EventRow
                  key={event.event_id}
                  event={event}
                  selected={event.event_id === selectedEvent?.event_id}
                  onSelect={() => setSelectedId(event.event_id)}
                />
              ))}
            </div>
            {eventsQuery.isLoading && (
              <p className={styles.emptyState}>Consultando eventos na API…</p>
            )}
            {eventsQuery.isError && (
              <p className={`${styles.emptyState} ${styles.error}`}>
                Não foi possível consultar a API. Tente novamente.
              </p>
            )}
            {!eventsQuery.isLoading &&
              !eventsQuery.isError &&
              filteredEvents.length === 0 && (
                <p className={styles.emptyState}>
                  Nenhum evento corresponde aos filtros selecionados.
                </p>
              )}
          </section>

          {selectedEvent && (
            <section className={styles.eventDetails}>
              <p>Evento selecionado</p>
              <div>
                <DetailField label="ID" value={selectedEvent.event_id} />
                <DetailField
                  label="Data"
                  value={formatDate(selectedEvent.occurred_at)}
                />
                <DetailField
                  label="Dispositivo"
                  value={selectedDevice || "não informado"}
                />
                <DetailField
                  label="Sistema"
                  value={platformName(selectedEvent)}
                />
                <DetailField
                  label="Rota"
                  value={selectedEvent.route_path ?? "não informada"}
                />
                <DetailField
                  label="Versão"
                  value={selectedEvent.app_version ?? "não informada"}
                />
              </div>
              <details>
                <summary>Ver atributos recebidos</summary>
                <pre>{JSON.stringify(selectedEvent.attributes, null, 2)}</pre>
              </details>
            </section>
          )}
      </div>
    </div>
  );
}
