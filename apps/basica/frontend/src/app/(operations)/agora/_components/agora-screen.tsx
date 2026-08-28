"use client";

import Link from "next/link";
import { useMemo, useRef, useState, type CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { normalizeQueryFailure } from "@/lib/operational-state";
import type { SignalDeviation } from "../_mocks/scenario";
import {
  fetchAgoraFacets,
  fetchSignals,
  toActiveDegradation,
  toOpenDegradation,
  toSignalDeviation,
} from "../_lib/signals-source";
import { agoraStyles as styles } from "./agora.styles";

/**
 * Dimensões da série que `GET /api/v1/signals` realmente aceita.
 *
 * Antes eram `plataforma`, `fabricante`, `região` e `app`. Aquelas colunas
 * existem em `bronze.event`, e não em `gold.v_feature_bucket`, que é a fonte
 * dos sinais — os quatro seletores ficavam interativos e não mudavam nada na
 * lista. Estas quatro são filtradas no SQL, e o filtro vale também para o
 * baseline.
 */
type FilterKey = "source" | "entity" | "metric" | "tem_jogo";
type Filters = Record<FilterKey, string>;

const initialFilters: Filters = {
  source: "all",
  entity: "all",
  metric: "all",
  tem_jogo: "all",
};

/** Visão operacional em tempo real, com sinais vindos de `GET /api/v1/signals`. */
export function AgoraScreen() {
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const [selectedSignal, setSelectedSignal] = useState<SignalDeviation | null>(null);
  const detailTriggerRef = useRef<HTMLButtonElement | null>(null);
  const { hrefWithDemoState } = useOperationsUi();

  const signals = useQuery({
    // Os filtros entram na chave: mudar o recorte é uma consulta diferente, e
    // não uma reordenação do que já veio. Sem isso o TanStack Query serviria o
    // resultado do recorte anterior enquanto busca o novo.
    queryKey: ["agora-signals", filters],
    queryFn: ({ signal }) => fetchSignals(filters, signal),
    refetchInterval: 30_000,
    // Uma segunda tentativa automática repete o timeout de 30 s da Lambda e
    // deixa a tela em loading por quase um minuto. O botão de retry continua
    // disponível para uma nova tentativa explícita.
    retry: false,
  });

  // Valores reais dos filtros -- consulta separada porque facets muda pouco
  // (staleTime mais longo) e não deve reexecutar junto com os sinais.
  const facets = useQuery({
    queryKey: ["agora-facets"],
    queryFn: ({ signal }) => fetchAgoraFacets(signal),
    staleTime: 5 * 60_000,
  });

  const items = useMemo(() => signals.data?.items ?? [], [signals.data]);
  // A filtragem acontece no SQL, não aqui: `fetchSignals` recebe o recorte e a
  // consulta já volta restrita. Filtrar em memória traria a janela inteira do
  // banco a cada polling de 30 s.
  const visibleSignals = useMemo(() => items.map(toSignalDeviation), [items]);
  const topSignal = items[0];
  const hasActiveDegradation = Boolean(topSignal && topSignal.severity !== "stable");
  const activeDegradation = topSignal ? toActiveDegradation(topSignal) : null;
  const openDegradations = useMemo(
    () => items.slice(1).filter((item) => item.severity !== "stable").map(toOpenDegradation),
    [items],
  );

  const sessionCounts = items.flatMap((item) =>
    item.sessions_impacted == null ? [] : [item.sessions_impacted],
  );
  const totalSessions = sessionCounts.reduce((sum, count) => sum + count, 0);
  const scopeSummary = signals.data
    ? `${items.length} sinal(is) ativo(s)${
        signals.data.truncated ? " (lista truncada)" : ""
      }${
        sessionCounts.length > 0
          ? ` · ${totalSessions.toLocaleString("pt-BR")} sessões atribuídas`
          : ""
      }`
    : undefined;

  function updateFilter(key: FilterKey, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function clearFilters() {
    setFilters(initialFilters);
  }

  // As opções saem de `/api/v1/series/facets`, a MESMA view que alimenta os
  // sinais. Assim todo valor oferecido é um valor que existe na série: um
  // seletor populado de outra tabela ofereceria recortes que nunca devolvem
  // resultado, e o operador leria isso como "não há problema agora".
  const filterDefinitions: Array<{ key: FilterKey; label: string; options: string[] }> = [
    { key: "source", label: "fonte", options: facets.data?.facets.source ?? [] },
    { key: "entity", label: "entidade", options: facets.data?.facets.entity ?? [] },
    { key: "metric", label: "métrica", options: facets.data?.facets.metric ?? [] },
    { key: "tem_jogo", label: "transmissão", options: facets.data?.facets.tem_jogo ?? [] },
  ];

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
        state: signals.isLoading
          ? "loading"
          : signals.isError && !signals.data
            ? "error"
            : signals.isError && signals.data
              ? "stale"
              : signals.isFetching && signals.data
                ? "refreshing"
                : signals.data && items.length === 0
                  ? "empty"
                  : "ready",
        title: "Sinais em desvio",
        scope: scopeSummary,
        failure: signals.error
          ? normalizeQueryFailure(
              signals.error,
              signals.dataUpdatedAt ? new Date(signals.dataUpdatedAt).toLocaleTimeString("pt-BR") : undefined,
            )
          : undefined,
        onRetry: () => signals.refetch(),
        onResetFilters: () => setFilters(initialFilters),
      }}
    >
      <div className={styles.page}>
          <section className={styles.hero} aria-labelledby="active-degradation-title">
            {hasActiveDegradation && activeDegradation ? (
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
                <p className={styles.eyebrow}>Sem degradação ativa</p>
                <h1 id="active-degradation-title">Nenhum incidente ativo no momento</h1>
                <p>
                  Os sinais ainda aparecem abaixo para comparação com seus baselines.
                </p>
                <Button type="button" variant="outline" onClick={() => signals.refetch()}>
                  Atualizar agora
                </Button>
              </div>
            )}
          </section>

          <section className={styles.signalsSection} aria-labelledby="signals-title">
            <header className={styles.sectionHeader}>
              <h2 id="signals-title">Sinais em desvio agora</h2>
              <p>ordenados por magnitude do desvio (z-score)</p>
              <span>GET /api/v1/signals</span>
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
                <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-panel border border-border bg-border text-sm">
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
