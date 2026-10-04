"use client";

/** Tela 04 — Hipóteses: causas prováveis ranqueadas e decomposição do score. */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Button } from "@/components/ui/button";
import { ScreenFrame, type ScreenPeriod } from "../../_components/screen-frame";
import { useOperationsUi } from "../../_components/operations-ui-context";
import { ALL_SCOPE_VALUES } from "../../_lib/scope-filters";
import { useSimClock, windowEndingAt } from "../../_lib/sim-clock";
import { normalizeQueryFailure } from "@/lib/operational-state";
import { fetchHypotheses } from "../_lib/hypotheses-source";
import { HYPOTHESIS_FILTERS, type HypothesisFilterKey } from "../_lib/mapper";
import { factorStrength } from "../_lib/score";
import {
  hypothesisRefinementEnabled,
  refineHypothesis,
} from "../_lib/refinement";
import type {
  DiscardedHypothesis,
  Hypothesis,
  HypothesesReport,
} from "../_lib/types";
import { hypothesisFeedbackEnabled } from "../_lib/feedback";
import { HypothesisVerdict } from "./hypothesis-verdict";
import { hipotesesStyles as styles } from "./hipoteses.styles";

/** Minutos de cada período, para converter o rótulo na janela consultada. */
const periodMinutes: Record<ScreenPeriod, number> = {
  "15 min": 15,
  "30 min": 30,
  "3 h": 180,
  "24 h": 1_440,
};

/** Tons da faixa de fatores, do mais para o menos determinante. */
const factorShades = [
  "var(--rank-1)",
  "var(--rank-2)",
  "var(--rank-3)",
  "var(--rank-4)",
];

type Filters = Record<HypothesisFilterKey, string>;

const initialFilters: Filters = {
  family: ALL_SCOPE_VALUES,
  kind: ALL_SCOPE_VALUES,
  confidence: ALL_SCOPE_VALUES,
  review_status: ALL_SCOPE_VALUES,
};

/** Converte os rótulos escolhidos nos valores que a API valida. */
function toApiScope(filters: Filters): Record<string, string> {
  const scope: Record<string, string> = {};
  for (const definition of HYPOTHESIS_FILTERS) {
    const value = definition.options[filters[definition.key]];
    if (value) scope[definition.key] = value;
  }
  return scope;
}

/** Causas prováveis do recorte, ranqueadas e com o score decomposto. */
export function HipotesesScreen() {
  const { period: sharedPeriod } = useOperationsUi();
  const clock = useSimClock();
  const period = sharedPeriod ?? "30 min";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Família, tipo e confiança são filtrados no SQL, e não aqui: a janela de
  // 24 h passa de mil hipóteses, quase todas de qualidade de dado, e filtrar em
  // memória obrigaria a paginar tudo antes de mostrar as dez que interessam.
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const activeFilters = Object.values(filters).filter((value) => value !== ALL_SCOPE_VALUES).length;
  const currentWindow = useMemo(
    () => clock.snapshot ? windowEndingAt(clock.snapshot.simNow, periodMinutes[period]) : null,
    [clock.snapshot, period],
  );

  const report = useInfiniteQuery({
    queryKey: ["hypotheses", period, currentWindow?.to, filters],
    queryFn: ({ pageParam, signal }) => fetchHypotheses({
      ...currentWindow!,
      cursor: pageParam ?? undefined,
      scope: toApiScope(filters),
    }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    enabled: Boolean(currentWindow),
    refetchInterval: 30_000,
  });
  const { hasNextPage, isFetching, isFetchNextPageError, fetchNextPage } = report;

  useEffect(() => {
    if (hasNextPage && !isFetching && !isFetchNextPageError) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetching, isFetchNextPageError, fetchNextPage]);

  const loadedReport = useMemo(() => {
    const pages = report.data?.pages;
    if (!pages?.length) return undefined;
    const hypotheses = pages.flatMap((page) => page.hypotheses);
    const families = new Set(hypotheses.map((item) => item.category));
    const sources = new Set(hypotheses.flatMap((item) => item.evidence.map((evidence) => evidence.source.split(":")[0])));
    return {
      ...pages[0],
      window: { ...pages[0].window, label: period },
      generated: hypotheses.length,
      summary: { hypotheses: hypotheses.length, families: families.size, sources: sources.size },
      hypotheses,
    };
  }, [report.data, period]);
  const hypotheses = useMemo(() => loadedReport?.hypotheses ?? [], [loadedReport]);
  const selected = hypotheses.find((item) => item.id === selectedId) ?? hypotheses[0] ?? null;

  return (
    <ScreenFrame
      filters={HYPOTHESIS_FILTERS.map((definition) => ({
        key: definition.key,
        label: definition.label,
        value: filters[definition.key],
        options: Object.keys(definition.options),
      }))}
      onFilterChange={(key, value) => setFilters((current) => ({ ...current, [key]: value }))}
      onClearFilters={() => setFilters(initialFilters)}
      scopeFilterCount={activeFilters}
      scopeSummary={scopeSummary(loadedReport)}
      operational={{
        state: clock.error && !clock.snapshot
          ? "error"
          : clock.isLoading || report.isLoading
          ? "loading"
          : report.isError && !loadedReport
            ? "error"
            : report.isError && loadedReport
              ? "stale"
              : report.isFetching && loadedReport
                ? "refreshing"
                : loadedReport && hypotheses.length === 0
                  ? "empty"
                  : "ready",
        title: "Hipóteses de causa provável",
        scope: scopeSummary(loadedReport),
        failure: clock.error
          ? normalizeQueryFailure(clock.error)
          : report.error
            ? normalizeQueryFailure(report.error, report.dataUpdatedAt ? new Date(report.dataUpdatedAt).toLocaleTimeString("pt-BR") : undefined)
            : undefined,
        onRetry: () => {
          clock.refetch();
          report.refetch();
        },
        // Só quando há filtro: sem nenhum, o vazio veio da janela, e "rever
        // filtros" não teria o que rever.
        onResetFilters: activeFilters > 0 ? () => setFilters(initialFilters) : undefined,
      }}
    >
      <header className={styles.header}>
        <h1>Hipóteses de causa provável</h1>
        {loadedReport && (
          <p>
            {loadedReport.generated}{report.hasNextPage ? "+" : ""} geradas
            {loadedReport.discarded > 0 && ` · ${loadedReport.discarded} descartadas`} · janela{" "}
            {loadedReport.window.label}
          </p>
        )}
      </header>

      {loadedReport && hypotheses.length > 0 && (
        <div className={styles.layout}>
          <section className={styles.list} aria-label="Hipóteses ranqueadas">
            <ol>
              {hypotheses.map((hypothesis, index) => (
                <li key={hypothesis.id}>
                  <HypothesisItem
                    hypothesis={hypothesis}
                    rank={index + 1}
                    selected={hypothesis.id === selected?.id}
                    onSelect={() => setSelectedId(hypothesis.id)}
                  />
                </li>
              ))}
            </ol>
            {/* Mostrar o que foi descartado é o que separa "avaliado e
                rejeitado" de "nunca considerado" -- sem isso o operador não
                consegue distinguir os dois casos. */}
            <DiscardedList items={loadedReport.discardedHypotheses} />
            {report.hasNextPage && (
              <Button type="button" variant="outline" disabled={report.isFetchingNextPage} onClick={() => void report.fetchNextPage()}>
                {report.isFetchingNextPage ? "Carregando hipóteses…" : "Carregar mais hipóteses"}
              </Button>
            )}
          </section>

          {selected && <ScorePanel key={selected.id} hypothesis={selected} />}
        </div>
      )}
    </ScreenFrame>
  );
}

/** Renderiza uma hipótese ranqueada e comunica a seleção ao callback. */
function HypothesisItem({
  hypothesis,
  rank,
  selected,
  onSelect,
}: {
  hypothesis: Hypothesis;
  rank: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={clsx(styles.item, selected && styles.selected)}
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
    >
      <strong className={clsx(styles.score, selected && "text-gradient-emphasis")}>{hypothesis.score}</strong>
      <span className={styles.body}>
        <span className={styles.kicker}>
          Hipótese {rank} · ID {hypothesis.id} · {hypothesis.category}
        </span>
        <span className={styles.title}>{hypothesis.title}</span>
        {/* Quando, onde e com que confiança: é o que distingue duas hipóteses
            de mesmo título e score sem precisar abrir cada uma. */}
        <span className={styles.meta}>
          {[
            hypothesis.effect,
            hypothesis.segment,
            `confiança ${hypothesis.confidence}`,
            hypothesis.reviewStatus !== "não revisada" && hypothesis.reviewStatus,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
        {/* A faixa tem o comprimento total do score e cada segmento vale a
            contribuição do seu fator: a comparação entre hipóteses e a
            composição de cada uma ficam legíveis na mesma marca. */}
        <span className={styles.strip} aria-hidden="true">
          {hypothesis.factors.map((factor, index) => (
            <i
              key={factor.id}
              style={{
                width: `${factor.contribution}%`,
                background: factorShades[index] ?? factorShades[factorShades.length - 1],
              }}
            />
          ))}
        </span>
      </span>
    </button>
  );
}

/** Renderiza as hipóteses avaliadas e rejeitadas com o motivo do descarte. */
function DiscardedList({ items }: { items: DiscardedHypothesis[] }) {
  if (items.length === 0) return null;

  return (
    <section className={styles.discarded}>
      <p>Descartadas</p>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <b>{String(item.score).padStart(2, "0")}</b>
            <span>
              <strong>{item.title}</strong> — {item.reason}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Renderiza a decomposição do score, as evidências e as ações da hipótese. */
function ScorePanel({ hypothesis }: { hypothesis: Hypothesis }) {
  const { hrefWithDemoState } = useOperationsUi();
  const refinement = useQuery({
    queryKey: ["hypothesis-refinement", hypothesis.id],
    queryFn: () => refineHypothesis(hypothesis.id),
    enabled: hypothesisRefinementEnabled,
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
  });
  const refinementFailure = refinement.isError
    ? normalizeQueryFailure(refinement.error)
    : null;
  return (
    <aside className={styles.panel} aria-label="Composição do score">
      <p className={styles.panelKicker}>Como este score foi calculado</p>
      <h2>{hypothesis.title}</h2>
      {hypothesis.summary && <p className={styles.summary}>{hypothesis.summary}</p>}

      <dl className={styles.facts}>
        <div><dt>Efeito</dt><dd>{hypothesis.effect ?? "sem instante"}</dd></div>
        <div><dt>Escopo</dt><dd>{hypothesis.segment}</dd></div>
        {hypothesis.kind && <div><dt>Tipo</dt><dd>{hypothesis.kind}</dd></div>}
        {hypothesis.coverage != null && (
          <div>
            <dt>Evidência disponível</dt>
            <dd>{Math.round(hypothesis.coverage * 100)}% do exigido pela família</dd>
          </div>
        )}
      </dl>

      <p className={styles.panelScore}>
        <strong className="text-gradient-emphasis">{hypothesis.score}</strong>
        <span>
          soma ponderada de {hypothesis.factors.length} fatores, normalizada em 0–100. Confiança{" "}
          {hypothesis.confidence}.
        </span>
      </p>

      <ul className={styles.factors}>
        {hypothesis.factors.map((factor) => (
          <li key={factor.id}>
            <div className={styles.factorHead}>
              <strong>{factor.label}</strong>
              <span>
                peso {factor.weight.toLocaleString("pt-BR", { minimumFractionDigits: 2 })} ·{" "}
                {factor.applicability === "available"
                  ? `contribui ${factor.contribution.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} pts`
                  : factor.applicability === "not_applicable"
                    ? "não se aplica"
                    : "indisponível"}
              </span>
            </div>
            <div className={styles.meter}>
              <i style={{ width: `${factorStrength(factor) * 100}%` }} />
            </div>
            <p>{factor.rationale}</p>
          </li>
        ))}
      </ul>

      <p className={styles.panelKicker}>Evidências consultadas</p>
      {hypothesis.evidence.length === 0 ? (
        <p className={styles.evidenceEmpty}>
          Nenhuma evidência registrada: a hipótese se apoia só nos fatores acima.
        </p>
      ) : (
        <ul className={styles.evidence}>
          {hypothesis.evidence.map((item) => (
            <li key={item.source}>
              <b>
                {item.polarity && (
                  <em className={clsx(item.polarity === "contra" && styles.contrary)}>{item.polarity}</em>
                )}
                {item.source}
                {item.at && <small>{item.at}</small>}
              </b>
              <span>{item.detail}</span>
            </li>
          ))}
        </ul>
      )}

      {hypothesisRefinementEnabled && (
        <section className={styles.refinement} aria-live="polite">
          <p className={styles.panelKicker}>Explicação refinada</p>
          {refinement.data ? (
            <>
              <p>{refinement.data.answer}</p>
              {refinement.data.sources.length > 0 && (
                <small>
                  Base exclusiva: {refinement.data.sources.map((source) => source.id).join(", ")}
                </small>
              )}
            </>
          ) : refinementFailure ? (
            <>
              <p role="alert">{refinementFailure.cause}</p>
              <small>Referencia: {refinementFailure.reference}</small>
              <Button type="button" variant="outline" size="sm" onClick={() => refinement.refetch()}>
                Tentar novamente
              </Button>
            </>
          ) : refinement.isLoading ? (
            <p>Refinando automaticamente com base apenas nesta hipótese...</p>
          ) : (
            <p>
              A explicação refinada ainda não está disponível.
            </p>
          )}
        </section>
      )}

      {hypothesisFeedbackEnabled && <HypothesisVerdict hypothesis={hypothesis} />}

      {/* As duas ações encadeiam os fluxos: a hipótese viaja na URL para que a
          timeline e o recorte abram já centrados nela. */}
      <div className={styles.actions}>
        <Button asChild>
          <Link href={hrefWithDemoState(`/timeline?hipotese=${hypothesis.id}&t=${encodeURIComponent(hypothesis.timelineAnchor)}`)}>
            Abrir na timeline
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href={hrefWithDemoState(`/recorte?hipotese=${hypothesis.id}&segmento=${encodeURIComponent(hypothesis.segment)}`)}>
            Ver recorte afetado
          </Link>
        </Button>
      </div>
    </aside>
  );
}

/** Formata a volumetria do recorte exibida à direita da barra de escopo.
 *
 * Conta hipótese, família e fonte -- e não sessão nem % de tráfego, que o
 * motor não calcula. Aqueles dois vinham do mock e não têm equivalente em
 * `gold.v_hypothesis`; exibi-los exigiria inventar número.
 */
function scopeSummary(report?: HypothesesReport): string | undefined {
  if (!report) return undefined;
  const { hypotheses, families, sources } = report.summary;
  return [
    `${hypotheses.toLocaleString("pt-BR")} ${hypotheses === 1 ? "hipótese" : "hipóteses"}`,
    `${families} ${families === 1 ? "família" : "famílias"}`,
    `${sources} ${sources === 1 ? "fonte cruzada" : "fontes cruzadas"}`,
  ].join(" · ");
}
