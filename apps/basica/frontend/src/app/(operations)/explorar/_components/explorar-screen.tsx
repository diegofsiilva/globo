"use client";

import { useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ScreenFrame,
} from "../../_components/screen-frame";
import { useOperationsUi } from "../../_components/operations-ui-context";
import { normalizeQueryFailure } from "@/lib/operational-state";
import type { EventKind, GroupBy } from "../_lib/types";
import {
  fetchBreakdown,
  fetchFacets,
  fetchTimeseries,
  type EventScope,
} from "../_lib/api";
import { formatEvents, groupByDimension, scopeFilterDefs } from "../_lib/exploration-config";
import {
  buildDenseTimeline,
  condenseTimeline,
  createAxisLabels,
  defaultRangeSteps,
  formatDuration,
  formatTimelinePoint,
  historyLastIndex,
  historyMinutes,
  historyStepMinutes,
  minimumRangeSteps,
  periodPresets,
} from "../_lib/timeline";
import { explorarStyles as styles } from "./explorar.styles";
import { ExplorationBreakdown } from "./exploration-breakdown";

/** Rótulo amigável dos seis tipos de evento mínimos do escopo do projeto. */
const EVENT_LABELS: Record<string, string> = {
  request: "Requisições",
  screen_view: "Telas exibidas",
  video_view: "Vídeos iniciados",
  session: "Sessões",
  vitals: "Sinais de qualidade",
  error: "Erros",
};

const FALLBACK_EVENT: EventKind = {
  id: "error",
  label: "error",
  name: "Erros",
  value: "—",
  count: 0,
};

/** Janela fixa de 24h terminando agora -- a mesma consultada por todas as chamadas desta tela. */
function dayWindow() {
  const to = new Date();
  return {
    from: new Date(to.getTime() - historyMinutes * 60_000).toISOString(),
    to: to.toISOString(),
  };
}

/** Visão de exploração de eventos com dados reais da API de leitura. */
export function ExplorarScreen() {
  const { period, setPeriod } = useOperationsUi();
  const [activeEvent, setActiveEvent] = useState("error");
  const [groupBy, setGroupBy] = useState<GroupBy>("Modelo");
  const [activeFilters, setActiveFilters] = useState<string[]>(
    scopeFilterDefs.map((filter) => filter.id),
  );
  const [showGuide, setShowGuide] = useState(true);
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [freeRange, setFreeRange] = useState<{ start: number; end: number } | null>(null);
  const eventTabsRef = useRef<(HTMLButtonElement | null)[]>([]);

  const facetsQuery = useQuery({
    queryKey: ["explorar", "facets"],
    queryFn: ({ signal }) => fetchFacets(scopeFilterDefs.map((filter) => filter.field), signal),
    staleTime: 5 * 60_000,
  });

  const resolvedFilters = useMemo(
    () =>
      scopeFilterDefs.map((filter) => ({
        ...filter,
        value: facetsQuery.data?.facets[filter.field]?.[0] ?? "",
      })),
    [facetsQuery.data],
  );

  const scope: EventScope = useMemo(() => {
    const result: Record<string, string> = {};
    for (const filter of resolvedFilters) {
      if (activeFilters.includes(filter.id) && filter.value) {
        result[filter.field] = filter.value;
      }
    }
    return result;
  }, [resolvedFilters, activeFilters]);

  const eventsQuery = useQuery({
    queryKey: ["explorar", "events", scope],
    queryFn: ({ signal }) => fetchBreakdown("event_name", dayWindow(), scope, signal),
    refetchInterval: 30_000,
  });

  const timeseriesQuery = useQuery({
    queryKey: ["explorar", "timeseries", scope],
    queryFn: ({ signal }) => fetchTimeseries(dayWindow(), historyStepMinutes, scope, signal),
    refetchInterval: 30_000,
  });

  const dimension = groupByDimension[groupBy];
  const totalBreakdownQuery = useQuery({
    queryKey: ["explorar", "breakdown", dimension, scope],
    queryFn: ({ signal }) => fetchBreakdown(dimension, dayWindow(), scope, signal),
    refetchInterval: 30_000,
  });
  const errorBreakdownQuery = useQuery({
    queryKey: ["explorar", "breakdown-error", dimension, scope],
    queryFn: ({ signal }) =>
      fetchBreakdown(dimension, dayWindow(), { ...scope, event_name: "error" }, signal),
    refetchInterval: 30_000,
  });

  const primaryQueries = [eventsQuery, timeseriesQuery, totalBreakdownQuery, errorBreakdownQuery];
  const isLoading = primaryQueries.some((query) => query.isLoading);
  const failedQuery = primaryQueries.find((query) => query.isError);
  const hasAnyData = primaryQueries.every((query) => query.data !== undefined);
  const isRefreshing = !isLoading && primaryQueries.some((query) => query.isFetching);

  // Ancora "agora" à última resposta da timeseries, não a cada re-render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const now = useMemo(() => new Date(), [timeseriesQuery.data]);

  const eventKinds: EventKind[] = useMemo(
    () =>
      (eventsQuery.data?.groups ?? []).map((group) => ({
        id: group.key,
        label: group.key,
        name: EVENT_LABELS[group.key] ?? group.key,
        value: formatEvents(group.count),
        count: group.count,
      })),
    [eventsQuery.data],
  );

  const presetMinutes = periodPresets.find((item) => item.label === period)?.minutes;
  const presetRangeSteps = presetMinutes ? presetMinutes / historyStepMinutes : defaultRangeSteps;
  const windowStart = period === null && freeRange ? freeRange.start : historyLastIndex - presetRangeSteps;
  const windowEnd = period === null && freeRange ? freeRange.end : historyLastIndex;

  const inactiveFilters = resolvedFilters.filter(
    (filter) => !activeFilters.includes(filter.id),
  );
  const selectedEvent = eventKinds.find((event) => event.id === activeEvent) ?? eventKinds[0] ?? FALLBACK_EVENT;

  const denseTimeline = useMemo(
    () => buildDenseTimeline(timeseriesQuery.data?.buckets ?? [], now),
    [timeseriesQuery.data, now],
  );
  const eventTimeline = useMemo(
    () =>
      denseTimeline.map((point) => ({
        bucketTs: point.bucketTs,
        events: point.byEventName[selectedEvent.id] ?? 0,
        errors: point.byEventName.error ?? 0,
      })),
    [denseTimeline, selectedEvent.id],
  );
  const previewTimeline = useMemo(() => condenseTimeline(denseTimeline.map((p) => ({ events: p.total, errors: p.byEventName.error ?? 0 })), 36), [denseTimeline]);
  const previewMaximum = Math.max(1, ...previewTimeline.map((point) => point.events + point.errors));

  const selectedTimeline = eventTimeline.slice(windowStart, windowEnd + 1);
  const visibleTimeline = condenseTimeline(selectedTimeline);
  const selectedMinutes = (windowEnd - windowStart) * historyStepMinutes;
  const selectedDuration = formatDuration(selectedMinutes);
  const windowStartPoint = denseTimeline[windowStart];
  const windowEndPoint = denseTimeline[windowEnd];
  const windowStartLabel = windowStartPoint ? formatTimelinePoint(windowStartPoint.bucketTs, now, true) : "--:--";
  const windowEndLabel = windowEndPoint ? formatTimelinePoint(windowEndPoint.bucketTs, now, true) : "--:--";
  const axisLabels = createAxisLabels(denseTimeline, windowStart, windowEnd, now);
  const firstVisibleError = selectedTimeline[0]?.errors ?? 0;
  const lastVisibleError = selectedTimeline.at(-1)?.errors ?? 0;
  const errorTrend =
    lastVisibleError > firstVisibleError * 1.25
      ? "aceleram no trecho final"
      : lastVisibleError < firstVisibleError * 0.75
        ? "recuam no trecho final"
        : "permanecem estáveis";
  const rangeStyle = {
    "--range-start": `${(windowStart / historyLastIndex) * 100}%`,
    "--range-end": `${(windowEnd / historyLastIndex) * 100}%`,
  } as CSSProperties;

  // "vs. ontem" não tem rota equivalente hoje (exigiria uma segunda consulta
  // de breakdown deslocada em 24h por grupo); mantido como indisponível até
  // existir esse endpoint.
  const rows = useMemo(() => {
    const errorByKey = new Map((errorBreakdownQuery.data?.groups ?? []).map((g) => [g.key, g.count]));
    return (totalBreakdownQuery.data?.groups ?? []).map((group) => ({
      label: group.key,
      events: group.count,
      errorRate: group.count > 0 ? ((errorByKey.get(group.key) ?? 0) / group.count) * 100 : 0,
      delta: "sem comparação",
    }));
  }, [totalBreakdownQuery.data, errorBreakdownQuery.data]);
  const maxEvents = Math.max(1, ...rows.map((row) => row.events));
  const leadingRow = rows.length
    ? rows.reduce((leading, row) => (row.errorRate > leading.errorRate ? row : leading))
    : { label: "—", errorRate: 0, events: 0, delta: "sem comparação" };
  const scopeSummary = totalBreakdownQuery.data
    ? `${formatEvents(totalBreakdownQuery.data.total)} eventos no recorte`
    : undefined;

  function removeFilter(id: string) {
    setActiveFilters((current) => current.filter((filterId) => filterId !== id));
  }

  function restoreFilter(id: string) {
    setActiveFilters((current) => [...current, id]);
    setShowFilterMenu(false);
  }

  /**
   * Move a seleção entre os botões de tipo de evento com as setas, Home e End,
   * mantendo o padrão de foco itinerante usado nos demais grupos de pastilha.
   */
  function onEventKeyDown(keyEvent: KeyboardEvent<HTMLDivElement>) {
    const current = eventKinds.findIndex((event) => event.id === activeEvent);
    if (current < 0 || eventKinds.length === 0) return;

    let next = current;
    if (keyEvent.key === "ArrowRight" || keyEvent.key === "ArrowDown") next = (current + 1) % eventKinds.length;
    else if (keyEvent.key === "ArrowLeft" || keyEvent.key === "ArrowUp") next = (current - 1 + eventKinds.length) % eventKinds.length;
    else if (keyEvent.key === "Home") next = 0;
    else if (keyEvent.key === "End") next = eventKinds.length - 1;
    else return;

    keyEvent.preventDefault();
    setActiveEvent(eventKinds[next].id);
    eventTabsRef.current[next]?.focus();
  }

  const scopeContent = (
    <div className={styles.filterList}>
      {resolvedFilters
        .filter((filter) => activeFilters.includes(filter.id))
        .map((filter) => (
          <div className={styles.filter} key={filter.id}>
            <span>{filter.label}</span>
            <strong>{filter.value || "carregando…"}</strong>
            <Button
              variant="ghost"
              size="icon-sm"
              type="button"
              aria-label={`Remover filtro ${filter.label}: ${filter.value}`}
              onClick={() => removeFilter(filter.id)}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
        ))}
      <div className={styles.addFilterWrap}>
        <Button
          className={styles.addFilter}
          variant="outline"
          size="sm"
          type="button"
          aria-expanded={showFilterMenu}
          onClick={() => setShowFilterMenu((current) => !current)}
        >
          <Plus aria-hidden="true" /> filtro
        </Button>
        {showFilterMenu && (
          <div className={styles.filterMenu}>
            {inactiveFilters.length ? (
              inactiveFilters.map((filter) => (
                <Button variant="ghost" type="button" key={filter.id} onClick={() => restoreFilter(filter.id)}>
                  <span>{filter.label}</span>{filter.value || "carregando…"}
                </Button>
              ))
            ) : (
              <p>Todos os filtros estão ativos.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <ScreenFrame
      scopeContent={scopeContent}
      scopeFilterCount={activeFilters.length}
      scopeSummary={scopeSummary}
      onClearFilters={() => setActiveFilters([])}
      operational={{
        state: isLoading
          ? "loading"
          : failedQuery && !hasAnyData
            ? "error"
            : failedQuery && hasAnyData
              ? "stale"
              : isRefreshing
                ? "refreshing"
                : hasAnyData && eventKinds.length === 0
                  ? "empty"
                  : "ready",
        title: "Exploração de eventos",
        scope: scopeSummary,
        failure: failedQuery?.error
          ? normalizeQueryFailure(
              failedQuery.error,
              failedQuery.dataUpdatedAt ? new Date(failedQuery.dataUpdatedAt).toLocaleTimeString("pt-BR") : undefined,
            )
          : undefined,
        onRetry: () => primaryQueries.forEach((query) => query.refetch()),
        onResetFilters: () => setActiveFilters(scopeFilterDefs.map((filter) => filter.id)),
      }}
    >
      <div className={styles.page}>
          <header className={styles.intro}>
            <div>
              <span className={styles.contextLabel}>Investigação do recorte</span>
              <h1>Explorar eventos</h1>
              <p>
                Descubra quando o comportamento mudou, onde ele se concentra e
                qual erro explica o sinal.
              </p>
            </div>
            <Button
              className={styles.guideToggle}
              variant="outline"
              size="sm"
              type="button"
              aria-expanded={showGuide}
              aria-controls="exploration-guide"
              onClick={() => setShowGuide((current) => !current)}
            >
              {showGuide ? "Ocultar guia" : "Como usar"}
            </Button>
          </header>

          {showGuide && (
            <section
              className={styles.guide}
              id="exploration-guide"
              aria-label="Como usar esta página"
            >
              <div>
                <span>1</span>
                <p><strong>Escolha o sinal</strong>O cartão escuro define o evento analisado.</p>
              </div>
              <div>
                <span>2</span>
                <p><strong>Ache a virada</strong>O vermelho mostra quando os erros cresceram.</p>
              </div>
              <div>
                <span>3</span>
                <p><strong>Encontre a concentração</strong>Troque a dimensão para localizar a origem.</p>
              </div>
            </section>
          )}

          <section className={styles.eventPicker} aria-labelledby="event-picker-title">
            <header className={styles.sectionHeading}>
              <span className={styles.stepIndex}>01</span>
              <div>
                <h2 id="event-picker-title">Escolha o tipo de evento</h2>
                <p>Este será o ponto de partida para o restante da análise.</p>
              </div>
              <strong>{selectedEvent.value} no recorte</strong>
            </header>
            <div
              className={styles.eventSummary}
              role="group"
              aria-labelledby="event-picker-title"
              onKeyDown={onEventKeyDown}
            >
            {eventKinds.map((event, index) => {
              const active = activeEvent === event.id;
              return (
                <button
                  type="button"
                  key={event.id}
                  ref={(node) => {
                    eventTabsRef.current[index] = node;
                  }}
                  aria-pressed={active}
                  tabIndex={active ? 0 : -1}
                  onClick={() => setActiveEvent(event.id)}
                >
                  <strong>{event.name}</strong>
                  <span>{event.label} · {event.value}</span>
                </button>
              );
            })}
            </div>
          </section>

          <section className={styles.timelineSection} aria-labelledby="timeline-title">
            <header className={styles.sectionHeading}>
              <span className={styles.stepIndex}>02</span>
              <div>
                <h2 id="timeline-title">Veja quando o comportamento mudou</h2>
                <p>
                  Use os atalhos ou ajuste livremente a janela nas últimas 24 horas.
                </p>
              </div>
              <strong>Recorte: {selectedDuration}</strong>
            </header>

            <div
              className={styles.chartScroller}
              tabIndex={0}
              role="region"
              aria-label={`Gráfico de ${selectedEvent.name} entre ${windowStartLabel} e ${windowEndLabel}.`}
            >
              <div className={styles.chart} aria-hidden="true">
                <div className={styles.bars}>
                  {visibleTimeline.map((bar, index) => {
                    const barStyle = {
                      "--event-height": `${bar.events}px`,
                      "--error-height": `${bar.errors}px`,
                    } as CSSProperties;

                    return (
                      <span
                        className={styles.bar}
                        style={barStyle}
                        key={`${bar.events}-${bar.errors}-${index}`}
                      >
                        <i className={styles.errorBar} />
                        <i className={styles.eventBar} />
                      </span>
                    );
                  })}
                </div>
                <div className={styles.axisLabels} aria-hidden="true">
                  {axisLabels.map(({ index, label }) => (
                    <span key={index}>{label}</span>
                  ))}
                </div>
              </div>
              <p className="sr-only">
                {visibleTimeline.map((bar, index) =>
                  `Ponto ${index + 1}: índice de volume ${bar.events + bar.errors} e índice de erro ${bar.errors}`,
                ).join("; ")}.
              </p>
            </div>

            <div
              className={styles.timeNavigator}
              style={rangeStyle}
              role="group"
              aria-label="Selecionar uma janela dentro das últimas 24 horas"
            >
              <div className={styles.navigatorSummary}>
                <span>Janela exibida</span>
                <output aria-live="polite">
                  <strong>{selectedDuration}</strong>
                  <small>{windowStartLabel} — {windowEndLabel}</small>
                </output>
              </div>

              <div className={styles.navigatorBody}>
                <div className={styles.timeRangeControl}>
                  <div className={styles.navigatorPreview} aria-hidden="true">
                    {previewTimeline.map((point, index) => (
                      <i
                        key={`${point.events}-${point.errors}-${index}`}
                        style={{
                          "--preview-height": `${Math.max(
                            3,
                            Math.round(
                              ((point.events + point.errors) / previewMaximum) * 28,
                            ),
                          )}px`,
                        } as CSSProperties}
                      />
                    ))}
                  </div>
                  <span className={styles.rangeSelection} aria-hidden="true" />
                  <span
                    className={clsx(styles.rangeShade, styles.rangeShadeStart)}
                    aria-hidden="true"
                  />
                  <span
                    className={clsx(styles.rangeShade, styles.rangeShadeEnd)}
                    aria-hidden="true"
                  />
                  <input
                    className={clsx(styles.rangeInput, styles.rangeStart)}
                    type="range"
                    name="window-start"
                    min={0}
                    max={historyLastIndex}
                    value={windowStart}
                    aria-label="Início da janela temporal"
                    aria-valuetext={windowStartLabel}
                    onChange={(event) => {
                      setPeriod(null);
                      setFreeRange({
                        start: Math.min(
                          Number(event.target.value),
                          windowEnd - minimumRangeSteps,
                        ),
                        end: windowEnd,
                      });
                    }}
                  />
                  <input
                    className={clsx(styles.rangeInput, styles.rangeEnd)}
                    type="range"
                    name="window-end"
                    min={0}
                    max={historyLastIndex}
                    value={windowEnd}
                    aria-label="Fim da janela temporal"
                    aria-valuetext={windowEndLabel}
                    onChange={(event) => {
                      setPeriod(null);
                      setFreeRange({
                        start: windowStart,
                        end: Math.max(
                          Number(event.target.value),
                          windowStart + minimumRangeSteps,
                        ),
                      });
                    }}
                  />
                </div>
                <div className={styles.rangeScale} aria-hidden="true">
                  <span>24 h atrás</span>
                  <small>Arraste as duas alças · mínimo de 15 min</small>
                  <span>agora</span>
                </div>
              </div>
            </div>

            <div className={styles.legend} aria-label="Legenda do gráfico">
              <span><i /> eventos</span>
              <span><i /> com erro</span>
            </div>
          </section>

          <aside className={styles.quickRead} aria-live="polite">
            <span>Leitura rápida</span>
            <p>
              <strong>
                Entre {windowStartLabel} e {windowEndLabel}, os erros {errorTrend}.
              </strong>{" "}
              Em {groupBy.toLocaleLowerCase("pt-BR")}, <b>{leadingRow.label}</b>{" "}
              lidera com {leadingRow.errorRate.toLocaleString("pt-BR", {
                maximumFractionDigits: 1,
                minimumFractionDigits: 1,
              })}% de erro.
            </p>
            <small>Agora troque a dimensão abaixo para testar onde o sinal se concentra.</small>
          </aside>

          <ExplorationBreakdown
            groupBy={groupBy}
            maxEvents={maxEvents}
            onGroupByChange={setGroupBy}
            rows={rows}
            selectedEventName={selectedEvent.name}
          />
      </div>
    </ScreenFrame>
  );
}
