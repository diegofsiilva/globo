"use client";

import Link from "next/link";
import { useMemo, useRef, useState, type CSSProperties } from "react";
import clsx from "clsx";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ScreenFrame,
  type ScreenFilter,
} from "../../_components/screen-frame";
import { useOperationsUi } from "../../_components/operations-ui-context";
import {
  activeDegradation,
  agoraFilters,
  openDegradations,
  signalDeviations,
  type SignalDeviation,
} from "../_mocks/scenario";
import { agoraStyles as styles } from "./agora.styles";

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
export function AgoraScreen() {
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [selectedSignal, setSelectedSignal] = useState<SignalDeviation | null>(null);
  const detailTriggerRef = useRef<HTMLButtonElement | null>(null);
  const { hrefWithDemoState } = useOperationsUi();

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

  const screenFilters: ScreenFilter[] = filterDefinitions.map((definition) => ({
    key: definition.key,
    label: definition.label,
    value: filters[definition.key],
    options: definition.options,
  }));

  return (
    <ScreenFrame
      filters={screenFilters}
      onFilterChange={(key, value) => updateFilter(key as FilterKey, value)}
      onClearFilters={clearFilters}
      scopeSummary={scopeSummary}
      operational={{
        title: "Sinais em desvio",
        scope: scopeSummary,
        onResetFilters: () => setFilters(initialFilters),
      }}
    >
      <div className={styles.page}>
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
                <Button asChild className={styles.primaryAction}>
                  <Link href={hrefWithDemoState("/hipoteses")}>Ver hipóteses ranqueadas <span aria-hidden="true">→</span></Link>
                </Button>
              </>
            ) : (
              <div className={styles.clearState}>
                <p className={styles.eyebrow}>Recorte sem degradação crítica</p>
                <h1 id="active-degradation-title">Nenhum incidente ativo neste escopo</h1>
                <p>
                  Os sinais ainda aparecem abaixo para comparação com seus baselines.
                </p>
                <Button type="button" variant="outline" onClick={() => setFilters(initialFilters)}>
                  Restaurar recorte principal
                </Button>
              </div>
            )}
          </section>

          <section className={styles.signalsSection} aria-labelledby="signals-title">
            <header className={styles.sectionHeader}>
              <h2 id="signals-title">Sinais em desvio agora</h2>
              <p>ordenados por sessões impactadas — não por magnitude do desvio</p>
              <span>Mock · snapshot 06 ago 2026</span>
            </header>

            <div className={`${styles.tableScroller} hidden md:block`}>
              <table className={styles.signalsTable}>
                <thead>
                  <tr>
                    <th scope="col" className="!w-[25%]">Métrica</th>
                    <th scope="col" className="!w-[16%]">Recorte</th>
                    <th scope="col">Agora</th>
                    <th scope="col">Baseline</th>
                    <th scope="col">Δ</th>
                    <th scope="col" className="!w-[11%]">Últimos 30 min</th>
                    <th scope="col">Sessões</th>
                    <th scope="col" className="!w-[13%]">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleSignals.map((signal) => {
                    const hotBars = signal.severity === "critical" ? 7 : 3;

                    return (
                      <tr key={signal.id}>
                        <th scope="row">
                          <span
                            className={clsx(styles.statusMarker, styles[signal.severity])}
                            aria-hidden="true"
                          />
                          <span className={styles.metricName}>{signal.title}</span>
                          <small>
                            {severityLabel(signal.severity)} · {signal.source} · {signal.metric}
                          </small>
                        </th>
                        <td>{signal.scope}</td>
                        <td
                          className={clsx(
                            signal.severity === "critical" && styles.dangerCell,
                          )}
                        >
                          {signal.current}
                        </td>
                        <td>{signal.baseline}</td>
                        <td className={styles.deltaCell}>{signal.delta}</td>
                        <td>
                          <span
                            className={styles.sparkline}
                            aria-hidden="true"
                          >
                            {signal.trend.map((point, index) => (
                              <i
                                key={`${signal.id}-${index}`}
                                className={clsx(
                                  index >= signal.trend.length - hotBars &&
                                    signal.severity !== "stable" &&
                                    styles.hotBar,
                                )}
                                style={{ "--bar-height": `${point}px` } as CSSProperties}
                              />
                            ))}
                          </span>
                        </td>
                        <td>{signal.sessions}</td>
                        <td>
                          <Button type="button" variant="ghost" size="sm" onClick={(event) => { detailTriggerRef.current = event.currentTarget; setSelectedSignal(signal); }}>
                            Ver detalhes
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-4 divide-y divide-border border-y border-border md:hidden" aria-label="Sinais em desvio">
              {visibleSignals.map((signal) => (
                <article className="grid gap-4 py-5" key={signal.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Badge variant={signal.severity === "critical" ? "destructive" : signal.severity === "warning" ? "warning" : "outline"}>
                        {severityLabel(signal.severity)}
                      </Badge>
                      <h3 className="mt-2 break-words text-base font-semibold">{signal.title}</h3>
                      <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{signal.source} · {signal.metric}</p>
                    </div>
                    <strong className={clsx("shrink-0 font-mono text-lg", signal.severity === "critical" && "text-critical")}>{signal.current}</strong>
                  </div>
                  <dl className="grid grid-cols-2 gap-3 font-mono text-xs">
                    <div><dt className="text-muted-foreground">Recorte</dt><dd className="mt-1 break-words">{signal.scope}</dd></div>
                    <div><dt className="text-muted-foreground">Baseline</dt><dd className="mt-1">{signal.baseline}</dd></div>
                    <div><dt className="text-muted-foreground">Variação</dt><dd className="mt-1 font-semibold">{signal.delta}</dd></div>
                    <div><dt className="text-muted-foreground">Sessões</dt><dd className="mt-1">{signal.sessions}</dd></div>
                  </dl>
                  <Button type="button" variant="outline" onClick={(event) => { detailTriggerRef.current = event.currentTarget; setSelectedSignal(signal); }}>Ver detalhes</Button>
                </article>
              ))}
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
                    className={clsx(
                      degradation.severity === "alto"
                        ? styles.highSeverity
                        : styles.warningSeverity,
                    )}
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
      </div>

      <Sheet open={Boolean(selectedSignal)} onOpenChange={(open) => !open && setSelectedSignal(null)}>
        <SheetContent
          side="right"
          className="overflow-y-auto sm:max-w-lg"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            detailTriggerRef.current?.focus();
          }}
        >
          {selectedSignal && (
            <>
              <SheetHeader>
                <Badge variant={selectedSignal.severity === "critical" ? "destructive" : selectedSignal.severity === "warning" ? "warning" : "outline"}>
                  {severityLabel(selectedSignal.severity)}
                </Badge>
                <SheetTitle className="break-words">{selectedSignal.title}</SheetTitle>
                <SheetDescription className="break-all">{selectedSignal.source} · {selectedSignal.metric}</SheetDescription>
              </SheetHeader>
              <div className="grid gap-6 px-4 pb-8">
                <dl className="grid grid-cols-2 gap-px border border-border bg-border text-sm">
                  {[
                    ["Valor atual", selectedSignal.current],
                    ["Baseline", selectedSignal.baseline],
                    ["Limiar", selectedSignal.threshold],
                    ["Período observado", `${selectedSignal.detectedAt} — ${selectedSignal.lastObservedAt}`],
                    ["Recorte", selectedSignal.scope],
                    ["Sessões", selectedSignal.sessions],
                  ].map(([label, value]) => (
                    <div className="min-w-0 bg-background p-3" key={label}>
                      <dt className="font-mono text-xs text-muted-foreground">{label}</dt>
                      <dd className="mt-1 break-words font-semibold">{value}</dd>
                    </div>
                  ))}
                </dl>
                <div>
                  <h3 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">Interpretação</h3>
                  <p className="mt-2 text-sm leading-6">{selectedSignal.interpretation}</p>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <Button asChild><Link href={hrefWithDemoState(selectedSignal.relatedPaths.timeline)}>Abrir na Timeline</Link></Button>
                  <Button asChild variant="outline"><Link href={hrefWithDemoState(selectedSignal.relatedPaths.cut)}>Ver no Recorte</Link></Button>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </ScreenFrame>
  );
}

function severityLabel(severity: SignalDeviation["severity"]): string {
  if (severity === "critical") return "Crítico";
  if (severity === "warning") return "Atenção";
  return "Estável";
}
