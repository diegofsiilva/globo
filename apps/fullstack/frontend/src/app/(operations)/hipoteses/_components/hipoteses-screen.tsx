"use client";

/** Tela 04 — Hipóteses: causas prováveis ranqueadas e decomposição do score. */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
import { groupHypotheses, type HypothesisGroup } from "../_lib/grouping";
import { HypothesisVerdict } from "./hypothesis-verdict";
import { hipotesesStyles as styles } from "./hipoteses.styles";

/** Minutos de cada período, para converter o rótulo na janela consultada. */
const periodMinutes: Record<ScreenPeriod, number> = {
  "15 min": 15,
  "30 min": 30,
  "3 h": 180,
  "24 h": 1_440,
  "72 h": 4_320,
};

/** Tons da faixa de fatores, do mais para o menos determinante. */
const factorShades = [
  "var(--rank-1)",
  "var(--rank-2)",
  "var(--rank-3)",
  "var(--rank-4)",
];

type Filters = Record<HypothesisFilterKey, string>;

/** Quantas ocorrências de um grupo o painel lista antes de resumir o resto. */
const MAX_OCCURRENCES = 12;

// A lista abre nas hipóteses OPERACIONAIS. As de qualidade de dado ("atraso na
// fonte") saem com score mais alto e são dezenas por janela: sem o recorte
// inicial elas ocupavam as primeiras centenas de linhas e a causa provável do
// incidente ficava enterrada. Continuam a um clique, no filtro "tipo".
const initialFilters: Filters = {
  family: ALL_SCOPE_VALUES,
  kind: "operacional",
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
  const { period: sharedPeriod, setPeriod, hrefWithDemoState } = useOperationsUi();
  const clock = useSimClock();
  const router = useRouter();
  const searchParams = useSearchParams();
  const period = sharedPeriod ?? "30 min";
  // "Ver hipóteses" de um sinal da tela Agora manda a fonte e a entidade na
  // URL. A rota filtra por evidência (`source`, `entity`), então a lista abre
  // só com o que diz respeito ao sinal, em vez de todas as hipóteses da janela.
  const sourceParam = searchParams.get("source");
  const entityParam = searchParams.get("entity");
  const signalScope = useMemo(() => {
    const scope: Record<string, string> = {};
    if (sourceParam) scope.source = sourceParam;
    if (entityParam) scope.entity = entityParam;
    return scope;
  }, [sourceParam, entityParam]);
  const signalLabel = Object.values(signalScope).join(" · ");
  const signalFilters = Object.keys(signalScope).length;
  // Do curto para 24 h, e de 24 h para o teto: dois passos bastam para cobrir
  // "agora há pouco", "hoje" e "nos últimos dias".
  const widerPeriod: ScreenPeriod | null =
    period === "72 h" ? null : period === "24 h" ? "72 h" : "24 h";
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Família, tipo e confiança são filtrados no SQL, e não aqui: a janela de
  // 24 h passa de mil hipóteses, quase todas de qualidade de dado, e filtrar em
  // memória obrigaria a paginar tudo antes de mostrar as dez que interessam.
  const [filters, setFilters] = useState<Filters>(initialFilters);
  const activeFilters = Object.values(filters).filter((value) => value !== ALL_SCOPE_VALUES).length;
  const filtersChanged = HYPOTHESIS_FILTERS.some(
    (definition) => filters[definition.key] !== initialFilters[definition.key],
  );
  const currentWindow = useMemo(
    () => clock.snapshot ? windowEndingAt(clock.snapshot.simNow, periodMinutes[period]) : null,
    [clock.snapshot, period],
  );

  // O recorte do sinal conta como filtro: no estado vazio a faixa de contexto
  // não aparece, e sem isto o operador ficaria preso numa lista vazia sem
  // saber que ela está restrita a uma fonte.
  function clearFilters() {
    setFilters(initialFilters);
    if (signalFilters > 0) router.replace("/hipoteses");
  }

  const report = useInfiniteQuery({
    queryKey: ["hypotheses", period, currentWindow?.to, filters, signalScope],
    queryFn: ({ pageParam, signal }) => fetchHypotheses({
      ...currentWindow!,
      cursor: pageParam ?? undefined,
      scope: { ...toApiScope(filters), ...signalScope },
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
  const groups = useMemo(() => groupHypotheses(hypotheses), [hypotheses]);
  const selected = hypotheses.find((item) => item.id === selectedId) ?? groups[0]?.lead ?? null;
  const selectedGroup = selected
    ? groups.find((group) => group.items.some((item) => item.id === selected.id))
    : undefined;

  return (
    <ScreenFrame
      filters={HYPOTHESIS_FILTERS.map((definition) => ({
        key: definition.key,
        label: definition.label,
        value: filters[definition.key],
        options: Object.keys(definition.options),
      }))}
      onFilterChange={(key, value) => setFilters((current) => ({ ...current, [key]: value }))}
      onClearFilters={clearFilters}
      scopeFilterCount={activeFilters + signalFilters}
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
        // Só quando há o que rever: com os filtros no padrão e sem recorte de
        // sinal, o botão não mudaria nada.
        onResetFilters: filtersChanged || signalFilters > 0 ? clearFilters : undefined,
        // O motor publica hipóteses a cada janela de processamento, e não a
        // cada minuto: nos 30 min do padrão a lista costuma vir vazia mesmo
        // havendo hipóteses de horas atrás. O vazio oferece o próximo passo.
        emptyAction: widerPeriod
          ? { label: `Ampliar para ${widerPeriod}`, onAction: () => setPeriod(widerPeriod) }
          : undefined,
      }}
    >
      <header className={styles.header}>
        <h1>Hipóteses de causa provável</h1>
        {loadedReport && (
          <p>
            {loadedReport.generated}{report.hasNextPage ? "+" : ""} geradas
            {groups.length < hypotheses.length && ` em ${groups.length} grupos`}
            {loadedReport.discarded > 0 && ` · ${loadedReport.discarded} descartadas`} · janela{" "}
            {loadedReport.window.label}
          </p>
        )}
      </header>

      {signalLabel && (
        <p className={styles.context}>
          <span>
            Só hipóteses com evidência em <strong>{signalLabel}</strong>
          </span>
          <Link href={hrefWithDemoState("/hipoteses")}>Ver todas</Link>
        </p>
      )}

      {loadedReport && hypotheses.length > 0 && (
        <div className={styles.layout}>
          <section className={styles.list} aria-label="Hipóteses ranqueadas">
            <ol>
              {groups.map((group, index) => (
                <li key={group.key}>
                  <HypothesisItem
                    group={group}
                    rank={index + 1}
                    selected={group === selectedGroup}
                    onSelect={() => setSelectedId(group.lead.id)}
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

          {selected && (
            <ScorePanel
              key={selected.id}
              hypothesis={selected}
              group={selectedGroup}
              onSelect={setSelectedId}
            />
          )}
        </div>
      )}
    </ScreenFrame>
  );
}

/** Renderiza um grupo de hipóteses ranqueado e comunica a seleção ao callback. */
function HypothesisItem({
  group,
  rank,
  selected,
  onSelect,
}: {
  group: HypothesisGroup;
  rank: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const hypothesis = group.lead;
  const occurrences = group.items.length;
  // Com várias ocorrências, o "quando" do item é o intervalo que elas cobrem.
  const when =
    occurrences > 1
      ? `${occurrences} ocorrências · ${group.firstAt} → ${group.lastAt}`
      : hypothesis.effect;
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
            when,
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
function ScorePanel({
  hypothesis,
  group,
  onSelect,
}: {
  hypothesis: Hypothesis;
  group?: HypothesisGroup;
  onSelect: (id: string) => void;
}) {
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
    // O painel rola por conta própria (ver `panel` em hipoteses.styles): ele é
    // mais alto que a tela, e preso ao topo sem rolagem própria a parte de baixo
    // -- evidências, veredito e as ações -- só aparecia depois de rolar a lista
    // inteira. O `top` desconta o cabeçalho fixo e a barra de escopo.
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

      {group && group.items.length > 1 && (
        <section className={styles.occurrences} aria-label="Ocorrências desta hipótese">
          <p className={styles.panelKicker}>{group.items.length} ocorrências no período</p>
          <ul>
            {group.items.slice(0, MAX_OCCURRENCES).map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  aria-pressed={item.id === hypothesis.id}
                  onClick={() => onSelect(item.id)}
                >
                  {item.effect ?? `ID ${item.id}`} <span>score {item.score}</span>
                </button>
              </li>
            ))}
          </ul>
          {group.items.length > MAX_OCCURRENCES && (
            <small>e mais {group.items.length - MAX_OCCURRENCES}, mais antigas</small>
          )}
        </section>
      )}

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

      {/* Só existe enquanto há algo a dizer. Sem o refinador configurado a
          consulta não devolve nada, e a caixa ficava em todas as hipóteses com
          "ainda não está disponível" -- espaço ocupado por uma não-informação. */}
      {hypothesisRefinementEnabled && (refinement.data || refinementFailure || refinement.isLoading) && (
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
          ) : (
            <p>Refinando automaticamente com base apenas nesta hipótese...</p>
          )}
        </section>
      )}

      {hypothesisFeedbackEnabled && <HypothesisVerdict hypothesis={hypothesis} />}

      {/* A hipótese viaja na URL para a Timeline abrir centrada no efeito. O
          antigo "Ver recorte afetado" saiu: o Recorte é dispositivo × hora da
          fonte de player, e o escopo de uma hipótese é serviço, entidade ou
          fluxo -- o link levava a uma grade que não tinha relação com ela. */}
      <div className={styles.actions}>
        <Button asChild>
          <Link href={hrefWithDemoState(`/timeline?hipotese=${hypothesis.id}&t=${encodeURIComponent(hypothesis.timelineAnchor)}`)}>
            Abrir na timeline
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
