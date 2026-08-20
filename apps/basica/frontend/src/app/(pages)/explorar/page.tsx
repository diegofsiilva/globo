"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { OperationsNavigation } from "@/components/operations-navigation";
import {
  eventKinds,
  explorationGroups,
  frequentErrors,
  timeline,
  type GroupBy,
} from "@/mocks/explorar";
import styles from "./explorar.module.css";

const periodPresets = [
  { label: "15 min", minutes: 15 },
  { label: "30 min", minutes: 30 },
  { label: "3 h", minutes: 180 },
  { label: "24 h", minutes: 1_440 },
] as const;
const groupOptions: GroupBy[] = ["Modelo", "UF", "ISP", "Versão", "Rota"];
const historyMinutes = 1_440;
const historyStepMinutes = 5;
const historyPointCount = historyMinutes / historyStepMinutes + 1;
const historyLastIndex = historyPointCount - 1;
const minimumRangeSteps = 15 / historyStepMinutes;
const defaultRangeSteps = 30 / historyStepMinutes;
const mockEndMinute = 20 * 60 + 11;

const eventProfiles: Record<
  string,
  { errorHeight: number; eventHeight: number; rate: number }
> = {
  request: { errorHeight: 0.18, eventHeight: 1.08, rate: 0.18 },
  "screen-view": { errorHeight: 0.12, eventHeight: 0.9, rate: 0.12 },
  "video-view": { errorHeight: 0.48, eventHeight: 0.96, rate: 0.48 },
  session: { errorHeight: 0.24, eventHeight: 0.82, rate: 0.24 },
  vitals: { errorHeight: 0.1, eventHeight: 0.7, rate: 0.1 },
  error: { errorHeight: 1, eventHeight: 1, rate: 1 },
};

const scopeFilters = [
  { id: "platform", label: "plataforma", value: "webOS 3.x" },
  { id: "manufacturer", label: "fabricante", value: "LG" },
  { id: "region", label: "região", value: "Nordeste" },
  { id: "app", label: "app", value: "2026.3.0" },
] as const;

function formatEvents(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

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
        Math.round((start.errors + (end.errors - start.errors) * progress) * variation),
      ),
      events: Math.max(
        8,
        Math.round((start.events + (end.events - start.events) * progress) * variation),
      ),
    };
  });
}

function condenseTimeline<T extends { errors: number; events: number }>(
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

function formatDuration(minutes: number) {
  if (minutes < 60) return `${minutes} min`;

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes ? `${hours} h ${remainingMinutes} min` : `${hours} h`;
}

function formatTimelinePoint(index: number, includeDay = false) {
  const absoluteMinute = mockEndMinute - historyMinutes + index * historyStepMinutes;
  const isYesterday = absoluteMinute < 0;
  const minuteOfDay = ((absoluteMinute % 1_440) + 1_440) % 1_440;
  const hours = Math.floor(minuteOfDay / 60).toString().padStart(2, "0");
  const minutes = (minuteOfDay % 60).toString().padStart(2, "0");
  const day = isYesterday ? "ontem" : "hoje";

  return `${includeDay || isYesterday ? `${day} · ` : ""}${hours}:${minutes}`;
}

function createAxisLabels(start: number, end: number) {
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

const historyTimeline = createHistoryTimeline();
const previewMaximum = Math.max(
  ...timeline.map((point) => point.events + point.errors),
);

/** Visão de exploração baseada em um snapshot estático de telemetria. */
export default function ExplorarPage() {
  const [clock, setClock] = useState("20:11:04");
  const [activeEvent, setActiveEvent] = useState("error");
  const [groupBy, setGroupBy] = useState<GroupBy>("Modelo");
  const [activeFilters, setActiveFilters] = useState<string[]>(
    scopeFilters.map((filter) => filter.id),
  );
  const [showGuide, setShowGuide] = useState(true);
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [search, setSearch] = useState("");
  const [windowStart, setWindowStart] = useState(
    historyLastIndex - defaultRangeSteps,
  );
  const [windowEnd, setWindowEnd] = useState(historyLastIndex);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setClock(new Date().toLocaleTimeString("pt-BR"));
    }, 1_000);

    return () => window.clearInterval(timer);
  }, []);

  const inactiveFilters = scopeFilters.filter(
    (filter) => !activeFilters.includes(filter.id),
  );
  const filteredErrors = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("pt-BR");

    if (!normalizedSearch) return frequentErrors;

    return frequentErrors.filter((error) =>
      error.name.toLocaleLowerCase("pt-BR").includes(normalizedSearch),
    );
  }, [search]);
  const selectedEvent =
    eventKinds.find((event) => event.id === activeEvent) ?? eventKinds[5];
  const eventProfile = eventProfiles[selectedEvent.id];
  const errorEventCount = eventKinds.find((event) => event.id === "error")?.count ?? 512_000;
  const eventScale = selectedEvent.count / errorEventCount;
  const eventTimeline = historyTimeline.map((bar) => ({
    errors: Math.max(1, Math.round(bar.errors * eventProfile.errorHeight)),
    events: Math.max(8, Math.round(bar.events * eventProfile.eventHeight)),
  }));
  const selectedTimeline = eventTimeline.slice(windowStart, windowEnd + 1);
  const visibleTimeline = condenseTimeline(selectedTimeline);
  const selectedMinutes = (windowEnd - windowStart) * historyStepMinutes;
  const selectedDuration = formatDuration(selectedMinutes);
  const windowStartLabel = formatTimelinePoint(windowStart, true);
  const windowEndLabel = formatTimelinePoint(windowEnd, true);
  const activePreset = windowEnd === historyLastIndex
    ? periodPresets.find((preset) => preset.minutes === selectedMinutes)?.label
    : undefined;
  const axisLabels = createAxisLabels(windowStart, windowEnd);
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
  const rows = explorationGroups[groupBy].map((row) => ({
    ...row,
    errorRate: Math.max(0.1, row.errorRate * eventProfile.rate),
    events: Math.round(row.events * eventScale),
  }));
  const maxEvents = Math.max(...rows.map((row) => row.events));
  const leadingRow = rows.reduce((leading, row) =>
    row.errorRate > leading.errorRate ? row : leading,
  );
  const scopeSummary = activeFilters.length === scopeFilters.length
    ? "41.209 sessões · 3,1% do tráfego · 6 fontes cruzadas"
    : `${Math.max(74_000, 402_110 - activeFilters.length * 77_725).toLocaleString("pt-BR")} sessões · escopo ampliado`;

  function removeFilter(id: string) {
    setActiveFilters((current) => current.filter((filterId) => filterId !== id));
  }

  function restoreFilter(id: string) {
    setActiveFilters((current) => [...current, id]);
    setShowFilterMenu(false);
  }

  function selectPreset(minutes: number) {
    const rangeSteps = minutes / historyStepMinutes;

    setWindowStart(historyLastIndex - rangeSteps);
    setWindowEnd(historyLastIndex);
  }

  return (
    <div className={styles.page}>
      <div className={styles.topControls} aria-label="Atualização e período">
        <p className={styles.liveStatus}>
          <span aria-hidden="true" />
          Ao vivo · {clock}
        </p>
        <div className={styles.periods} aria-label="Atalhos de período">
          {periodPresets.map((preset) => (
            <button
              key={preset.label}
              type="button"
              aria-pressed={activePreset === preset.label}
              onClick={() => selectPreset(preset.minutes)}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <section className={styles.scopeBar} aria-label="Filtros do recorte">
        <span className={styles.scopeLabel}>Escopo</span>
        <div className={styles.filterList}>
          {scopeFilters
            .filter((filter) => activeFilters.includes(filter.id))
            .map((filter) => (
              <div className={styles.filter} key={filter.id}>
                <span>{filter.label}</span>
                <strong>{filter.value}</strong>
                <button
                  type="button"
                  aria-label={`Remover filtro ${filter.label}: ${filter.value}`}
                  onClick={() => removeFilter(filter.id)}
                >
                  ×
                </button>
              </div>
            ))}
          <div className={styles.addFilterWrap}>
            <button
              className={styles.addFilter}
              type="button"
              aria-expanded={showFilterMenu}
              onClick={() => setShowFilterMenu((current) => !current)}
            >
              + filtro
            </button>
            {showFilterMenu && (
              <div className={styles.filterMenu}>
                {inactiveFilters.length ? (
                  inactiveFilters.map((filter) => (
                    <button
                      type="button"
                      key={filter.id}
                      onClick={() => restoreFilter(filter.id)}
                    >
                      <span>{filter.label}</span>
                      {filter.value}
                    </button>
                  ))
                ) : (
                  <p>Todos os filtros estão ativos.</p>
                )}
              </div>
            )}
          </div>
        </div>
        <div className={styles.scopeMeta}>
          <span>{scopeSummary}</span>
          <button
            type="button"
            onClick={() => setActiveFilters([])}
            disabled={activeFilters.length === 0}
          >
            limpar
          </button>
        </div>
      </section>

      <div className={styles.workspace}>
        <OperationsNavigation />

        <main className={styles.content} id="main-content">
          <header className={styles.intro}>
            <div>
              <span className={styles.contextLabel}>Investigação do recorte</span>
              <h1>Explorar eventos</h1>
              <p>
                Descubra quando o comportamento mudou, onde ele se concentra e
                qual erro explica o sinal.
              </p>
            </div>
            <button
              className={styles.guideToggle}
              type="button"
              aria-expanded={showGuide}
              aria-controls="exploration-guide"
              onClick={() => setShowGuide((current) => !current)}
            >
              {showGuide ? "Ocultar guia" : "Como usar"}
            </button>
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
            <div className={styles.eventSummary}>
            {eventKinds.map((event) => (
              <button
                type="button"
                key={event.id}
                aria-pressed={activeEvent === event.id}
                onClick={() => setActiveEvent(event.id)}
              >
                <strong>{event.name}</strong>
                <span>{event.label} · {event.value}</span>
              </button>
            ))}
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
              <strong>Recorte: {selectedDuration} · atualizado há 4s</strong>
            </header>

            <div
              className={styles.chartScroller}
              tabIndex={0}
              role="region"
              aria-label={`Gráfico de ${selectedEvent.name} entre ${windowStartLabel} e ${windowEndLabel}.`}
            >
              <div className={styles.chart}>
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
                        title={`Índice de volume ${bar.events + bar.errors}; índice de erro ${bar.errors}`}
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
                    {timeline.map((point, index) => (
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
                    className={`${styles.rangeShade} ${styles.rangeShadeStart}`}
                    aria-hidden="true"
                  />
                  <span
                    className={`${styles.rangeShade} ${styles.rangeShadeEnd}`}
                    aria-hidden="true"
                  />
                  <input
                    className={`${styles.rangeInput} ${styles.rangeStart}`}
                    type="range"
                    min={0}
                    max={historyLastIndex}
                    value={windowStart}
                    aria-label="Início da janela temporal"
                    aria-valuetext={windowStartLabel}
                    onChange={(event) =>
                      setWindowStart(
                        Math.min(
                          Number(event.target.value),
                          windowEnd - minimumRangeSteps,
                        ),
                      )
                    }
                  />
                  <input
                    className={`${styles.rangeInput} ${styles.rangeEnd}`}
                    type="range"
                    min={0}
                    max={historyLastIndex}
                    value={windowEnd}
                    aria-label="Fim da janela temporal"
                    aria-valuetext={windowEndLabel}
                    onChange={(event) =>
                      setWindowEnd(
                        Math.max(
                          Number(event.target.value),
                          windowStart + minimumRangeSteps,
                        ),
                      )
                    }
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

          <section className={styles.breakdownSection} aria-labelledby="breakdown-title">
            <header className={styles.breakdownHeader}>
              <div className={styles.sectionHeading}>
                <span className={styles.stepIndex}>03</span>
                <div>
                  <h2 id="breakdown-title">Descubra onde o sinal se concentra</h2>
                  <p>A tabela muda conforme a dimensão escolhida.</p>
                </div>
              </div>
              <div className={styles.groupBar} aria-label="Quebrar resultado por">
                <span>Quebrar por</span>
                <div>
                  {groupOptions.map((option) => (
                    <button
                      type="button"
                      key={option}
                      aria-pressed={groupBy === option}
                      onClick={() => setGroupBy(option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
            </header>

            <div className={styles.results}>
              <div
                className={styles.distribution}
                tabIndex={0}
                role="region"
                aria-label={`Concentração de ${selectedEvent.name} por ${groupBy}`}
              >
                <table className={styles.distributionTable}>
                  <caption>
                    Eventos de {selectedEvent.name} agrupados por {groupBy}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">{groupBy}</th>
                      <th scope="col">Eventos</th>
                      <th scope="col" title="Percentual de eventos que apresentaram erro">
                        Taxa de erro
                      </th>
                      <th scope="col" title="Volume relativo dentro deste agrupamento">
                        Volume relativo
                      </th>
                      <th scope="col">vs. ontem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const critical = row.errorRate >= 10;
                      const width = Math.max(12, (row.events / maxEvents) * 96);

                      return (
                        <tr key={row.label}>
                          <th scope="row" title={row.label}>{row.label}</th>
                          <td>{formatEvents(row.events)}</td>
                          <td className={critical ? styles.errorValue : undefined}>
                            {row.errorRate.toLocaleString("pt-BR", {
                              maximumFractionDigits: 1,
                              minimumFractionDigits: 1,
                            })}%
                            {critical && <small>alto</small>}
                          </td>
                          <td>
                            <span
                              className={styles.distributionBar}
                              role="img"
                              aria-label={`${Math.round(width)}% do maior volume deste grupo`}
                            >
                              <i
                                className={critical ? styles.criticalFill : undefined}
                                style={{ width: `${width}%` }}
                              />
                            </span>
                          </td>
                          <td className={critical ? styles.errorValue : undefined}>
                            {row.delta}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <aside className={styles.errorsPanel} aria-labelledby="errors-title">
                <header className={styles.errorsHeader}>
                  <span className={styles.stepIndex}>04</span>
                  <div>
                    <h2 id="errors-title">Entenda o que falhou</h2>
                    <p>Veja quais mensagens explicam o recorte selecionado.</p>
                  </div>
                </header>
                <label htmlFor="error-search">Filtrar erros pelo nome</label>
                <input
                  id="error-search"
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Ex.: playback, timeout..."
                />
                <small className={styles.searchHint}>
                  Procure por parte do nome técnico do erro.
                </small>
                <h3>Erros mais frequentes</h3>
                <div className={styles.errorList}>
                  {filteredErrors.map((error) => (
                    <article key={error.id}>
                      <strong>{error.name}</strong>
                      <span>{error.count} · {error.share}</span>
                    </article>
                  ))}
                  {filteredErrors.length === 0 && (
                    <p className={styles.emptySearch}>Nenhum erro encontrado.</p>
                  )}
                </div>
              </aside>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
