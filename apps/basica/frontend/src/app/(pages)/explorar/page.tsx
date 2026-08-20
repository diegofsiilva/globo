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

const periods = ["15 min", "30 min", "3 h", "24 h"] as const;
const groupOptions: GroupBy[] = ["Modelo", "UF", "ISP", "Versão", "Rota"];

const scopeFilters = [
  { id: "platform", label: "plataforma", value: "webOS 3.x" },
  { id: "manufacturer", label: "fabricante", value: "LG" },
  { id: "region", label: "região", value: "Nordeste" },
  { id: "app", label: "app", value: "2026.3.0" },
] as const;

function formatEvents(value: number) {
  return new Intl.NumberFormat("pt-BR").format(value);
}

/** Visão de exploração baseada em um snapshot estático de telemetria. */
export default function ExplorarPage() {
  const [period, setPeriod] = useState<(typeof periods)[number]>("30 min");
  const [clock, setClock] = useState("20:11:04");
  const [activeEvent, setActiveEvent] = useState("error");
  const [groupBy, setGroupBy] = useState<GroupBy>("Modelo");
  const [activeFilters, setActiveFilters] = useState<string[]>(
    scopeFilters.map((filter) => filter.id),
  );
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [search, setSearch] = useState("");

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
  const rows = explorationGroups[groupBy];
  const maxEvents = Math.max(...rows.map((row) => row.events));
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

  return (
    <div className={styles.page}>
      <div className={styles.topControls} aria-label="Atualização e período">
        <p className={styles.liveStatus}>
          <span aria-hidden="true" />
          Ao vivo · {clock}
        </p>
        <div className={styles.periods} aria-label="Período analisado">
          {periods.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={period === value}
              onClick={() => setPeriod(value)}
            >
              {value}
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
            <h1>Explorar eventos</h1>
            <p>Os filtros do escopo já estão aplicados. Tudo abaixo é cumulativo.</p>
          </header>

          <section className={styles.eventSummary} aria-label="Tipos de evento">
            {eventKinds.map((event) => (
              <button
                type="button"
                key={event.id}
                aria-pressed={activeEvent === event.id}
                onClick={() => setActiveEvent(event.id)}
              >
                <strong>{event.label}</strong>
                <span>{event.value}</span>
              </button>
            ))}
          </section>

          <section className={styles.timelineSection} aria-labelledby="timeline-title">
            <div className={styles.groupBar}>
              <p id="timeline-title">Agrupar por</p>
              <div aria-label="Dimensão do agrupamento">
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
              <span>512.402 eventos · 8 grupos · atualizado há 4s</span>
            </div>

            <div
              className={styles.chartScroller}
              tabIndex={0}
              role="region"
              aria-label="Eventos e erros entre 19:11 e 20:11"
            >
              <div className={styles.chart}>
                <div className={styles.bars}>
                  {timeline.map((bar, index) => {
                    const barStyle = {
                      "--event-height": `${bar.events}px`,
                      "--error-height": `${bar.errors}px`,
                    } as CSSProperties;

                    return (
                      <span
                        className={styles.bar}
                        style={barStyle}
                        key={`${bar.events}-${bar.errors}-${index}`}
                        title={`${bar.events + bar.errors} mil eventos; ${bar.errors} mil com erro`}
                      >
                        <i className={styles.errorBar} />
                        <i className={styles.eventBar} />
                      </span>
                    );
                  })}
                </div>
                <div className={styles.axisLabels} aria-hidden="true">
                  <span>19:11</span>
                  <span>19:30</span>
                  <span>19:45</span>
                  <span>20:00</span>
                  <span>20:11</span>
                </div>
              </div>
            </div>

            <div className={styles.legend} aria-label="Legenda do gráfico">
              <span><i /> eventos</span>
              <span><i /> com erro</span>
            </div>
          </section>

          <section className={styles.results} aria-label="Distribuição e erros">
            <div className={styles.distribution}>
              <div className={styles.tableHead}>
                <span>{groupBy}</span>
                <span>Eventos</span>
                <span>Erro %</span>
                <span>Distribuição</span>
                <span>Δ vs ontem</span>
              </div>
              <div className={styles.tableBody}>
                {rows.map((row) => {
                  const critical = row.errorRate >= 10;
                  const width = Math.max(12, (row.events / maxEvents) * 96);

                  return (
                    <div className={styles.dataRow} key={row.label}>
                      <strong title={row.label}>{row.label}</strong>
                      <span>{formatEvents(row.events)}</span>
                      <span className={critical ? styles.errorValue : undefined}>
                        {row.errorRate.toLocaleString("pt-BR", {
                          minimumFractionDigits: 1,
                        })}%
                      </span>
                      <span className={styles.distributionBar} aria-hidden="true">
                        <i
                          className={critical ? styles.criticalFill : undefined}
                          style={{ width: `${width}%` }}
                        />
                      </span>
                      <span className={critical ? styles.errorValue : undefined}>
                        {row.delta}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            <aside className={styles.errorsPanel} aria-labelledby="errors-title">
              <label htmlFor="error-search">Buscar em atributos</label>
              <input
                id="error-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="error_name, url, modelo..."
              />
              <h2 id="errors-title">Erros mais frequentes</h2>
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
          </section>
        </main>
      </div>
    </div>
  );
}
