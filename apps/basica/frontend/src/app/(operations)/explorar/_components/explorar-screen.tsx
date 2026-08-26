"use client";

import { useState, type CSSProperties } from "react";
import clsx from "clsx";
import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ScreenFrame,
  type ScreenPeriod,
} from "../../_components/screen-frame";
import {
  eventKinds,
  explorationGroups,
  timeline,
  type GroupBy,
} from "../_mocks/scenario";
import { eventProfiles, scopeFilters } from "../_lib/exploration-config";
import {
  condenseTimeline,
  createAxisLabels,
  defaultRangeSteps,
  formatDuration,
  formatTimelinePoint,
  historyLastIndex,
  historyStepMinutes,
  historyTimeline,
  minimumRangeSteps,
  periodPresets,
  previewMaximum,
} from "../_lib/timeline";
import { explorarStyles as styles } from "./explorar.styles";
import { ExplorationBreakdown } from "./exploration-breakdown";

/** Visão de exploração baseada em um snapshot estático de telemetria. */
export function ExplorarScreen() {
  const [activeEvent, setActiveEvent] = useState("error");
  const [groupBy, setGroupBy] = useState<GroupBy>("Modelo");
  const [activeFilters, setActiveFilters] = useState<string[]>(
    scopeFilters.map((filter) => filter.id),
  );
  const [showGuide, setShowGuide] = useState(true);
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [windowStart, setWindowStart] = useState(
    historyLastIndex - defaultRangeSteps,
  );
  const [windowEnd, setWindowEnd] = useState(historyLastIndex);

  const inactiveFilters = scopeFilters.filter(
    (filter) => !activeFilters.includes(filter.id),
  );
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

  const scopeContent = (
    <div className={styles.filterList}>
      {scopeFilters
        .filter((filter) => activeFilters.includes(filter.id))
        .map((filter) => (
          <div className={styles.filter} key={filter.id}>
            <span>{filter.label}</span>
            <strong>{filter.value}</strong>
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
                  <span>{filter.label}</span>{filter.value}
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
      period={(activePreset as ScreenPeriod | undefined) ?? null}
      onPeriodChange={(value) => {
        const preset = periodPresets.find((item) => item.label === value);
        if (preset) selectPreset(preset.minutes);
      }}
      scopeContent={scopeContent}
      scopeSummary={scopeSummary}
      onClearFilters={() => setActiveFilters([])}
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
                    className={clsx(styles.rangeInput, styles.rangeEnd)}
                    type="range"
                    name="window-end"
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
