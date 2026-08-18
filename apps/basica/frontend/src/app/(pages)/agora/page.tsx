"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { OperationsNavigation } from "@/components/operations-navigation";
import {
  activeDegradation,
  agoraFilters,
  openDegradations,
  signalDeviations,
} from "@/mocks/agora";
import styles from "./agora.module.css";

const periods = ["15 min", "30 min", "3 h", "24 h"] as const;

type FilterKey = "app" | "manufacturer" | "platform" | "region";
type Filters = Record<FilterKey, string>;

const initialFilters: Filters = {
  app: "2026.3.0",
  manufacturer: "LG",
  platform: "webOS 3.x",
  region: "Nordeste",
};

const filterDefinitions: Array<{
  key: FilterKey;
  label: string;
  options: string[];
}> = [
  { key: "platform", label: "plataforma", options: agoraFilters.platforms },
  {
    key: "manufacturer",
    label: "fabricante",
    options: agoraFilters.manufacturers,
  },
  { key: "region", label: "região", options: agoraFilters.regions },
  { key: "app", label: "app", options: agoraFilters.apps },
];

/** Visão operacional em tempo real baseada em um recorte mock do dataset Argus. */
export default function AgoraPage() {
  const [period, setPeriod] = useState<(typeof periods)[number]>("30 min");
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [clock, setClock] = useState("20:11:04");

  useEffect(() => {
    const timer = window.setInterval(() => {
      setClock(new Date().toLocaleTimeString("pt-BR"));
    }, 1_000);

    return () => window.clearInterval(timer);
  }, []);

  const isIncidentScope =
    filters.platform === initialFilters.platform &&
    filters.manufacturer === initialFilters.manufacturer &&
    filters.region === initialFilters.region;

  const visibleSignals = useMemo(
    () =>
      isIncidentScope
        ? signalDeviations
        : signalDeviations.filter((signal) => signal.severity !== "critical"),
    [isIncidentScope],
  );
  const scopeSummary = isIncidentScope
    ? "41.209 sessões · 3,1% do tráfego · 6 fontes cruzadas"
    : filters.platform === "all"
      ? "402.110 sessões · 100% do tráfego · 6 fontes cruzadas"
      : "96.500 sessões · 7,3% do tráfego · 4 fontes cruzadas";

  function updateFilter(key: FilterKey, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function clearFilters() {
    setFilters({ app: "all", manufacturer: "all", platform: "all", region: "all" });
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
          {filterDefinitions.map((definition) => (
            <label className={styles.filter} key={definition.key}>
              <span>{definition.label}</span>
              <select
                aria-label={`Filtrar por ${definition.label}`}
                value={filters[definition.key]}
                onChange={(event) => updateFilter(definition.key, event.target.value)}
              >
                <option value="all">todos</option>
                {definition.options.map((option) => (
                  <option value={option} key={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <div className={styles.scopeMeta}>
          <span>{scopeSummary}</span>
          <button type="button" onClick={clearFilters}>
            limpar
          </button>
        </div>
      </section>

      <div className={styles.workspace}>
        <OperationsNavigation />

        <main className={styles.content} id="main-content">
          <section className={styles.hero} aria-labelledby="active-degradation-title">
            {isIncidentScope ? (
              <>
                <p className={styles.eyebrow}>
                  <span aria-hidden="true" />
                  Degradação ativa
                  <small>
                    detectada às {activeDegradation.detectedAt} · há{" "}
                    {activeDegradation.openFor}
                  </small>
                </p>
                <h1 id="active-degradation-title">
                  {activeDegradation.title.split("\n").map((line) => (
                    <span key={line}>{line}</span>
                  ))}
                </h1>
                <div className={styles.heroMetrics}>
                  <div>
                    <strong className={styles.dangerValue}>
                      {activeDegradation.failureRate}
                    </strong>
                    <span>falha de play</span>
                  </div>
                  <div>
                    <strong>{activeDegradation.impactedSessions}</strong>
                    <span>sessões no recorte</span>
                  </div>
                  <div>
                    <strong>{activeDegradation.baselineMultiplier}</strong>
                    <span>vs. baseline</span>
                  </div>
                  <div>
                    <strong>{activeDegradation.openFor}</strong>
                    <span>sem reclamação aberta</span>
                  </div>
                </div>
                <Link className={styles.primaryAction} href="/hipoteses">
                  Ver hipóteses ranqueadas <span aria-hidden="true">→</span>
                </Link>
              </>
            ) : (
              <div className={styles.clearState}>
                <p className={styles.eyebrow}>Recorte sem degradação crítica</p>
                <h1 id="active-degradation-title">Nenhum incidente ativo neste escopo</h1>
                <p>
                  Os sinais ainda aparecem abaixo para comparação com seus baselines.
                </p>
                <button type="button" onClick={() => setFilters(initialFilters)}>
                  Restaurar recorte principal
                </button>
              </div>
            )}
          </section>

          <section className={styles.signalsSection} aria-labelledby="signals-title">
            <header className={styles.sectionHeader}>
              <h2 id="signals-title">Sinais em desvio agora</h2>
              <p>ordenados por sessões impactadas — não por magnitude do desvio</p>
              <span>Mock · snapshot 06 ago 2026</span>
            </header>

            <div
              className={styles.tableScroller}
              tabIndex={0}
              role="region"
              aria-label="Tabela de sinais em desvio; role horizontalmente para ver todas as colunas"
            >
              <table className={styles.signalsTable}>
                <thead>
                  <tr>
                    <th scope="col">Métrica</th>
                    <th scope="col">Recorte</th>
                    <th scope="col">Agora</th>
                    <th scope="col">Baseline</th>
                    <th scope="col">Δ</th>
                    <th scope="col">Últimos 30 min</th>
                    <th scope="col">Sessões</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleSignals.map((signal) => {
                    const hotBars = signal.severity === "critical" ? 7 : 3;

                    return (
                      <tr key={signal.id}>
                        <th scope="row">
                          <span
                            className={`${styles.statusMarker} ${
                              styles[signal.severity]
                            }`}
                            aria-hidden="true"
                          />
                          <span className={styles.metricName}>{signal.title}</span>
                          <small>
                            {signal.source} · {signal.metric}
                          </small>
                        </th>
                        <td>{signal.scope}</td>
                        <td
                          className={
                            signal.severity === "critical" ? styles.dangerCell : ""
                          }
                        >
                          {signal.current}
                        </td>
                        <td>{signal.baseline}</td>
                        <td className={styles.deltaCell}>{signal.delta}</td>
                        <td>
                          <span
                            className={styles.sparkline}
                            role="img"
                            aria-label={`Tendência recente de ${signal.title}: ${signal.delta}`}
                          >
                            {signal.trend.map((point, index) => (
                              <i
                                key={`${signal.id}-${index}`}
                                className={
                                  index >= signal.trend.length - hotBars &&
                                  signal.severity !== "stable"
                                    ? styles.hotBar
                                    : undefined
                                }
                                style={{ "--bar-height": `${point}px` } as CSSProperties}
                              />
                            ))}
                          </span>
                        </td>
                        <td>{signal.sessions}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className={styles.openSection} aria-labelledby="open-title">
            <header>
              <p id="open-title">Outras degradações abertas</p>
              <span>{openDegradations.length} acompanhamentos</span>
            </header>
            <div className={styles.degradationList}>
              {openDegradations.map((degradation) => (
                <article key={degradation.id}>
                  <strong
                    className={
                      degradation.severity === "alto"
                        ? styles.highSeverity
                        : styles.warningSeverity
                    }
                  >
                    {degradation.severity}
                  </strong>
                  <div>
                    <h3>{degradation.title}</h3>
                    <p>{degradation.description}</p>
                    <small>
                      aberta às {degradation.openedAt} · {degradation.scope} ·{" "}
                      {degradation.source}
                    </small>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
