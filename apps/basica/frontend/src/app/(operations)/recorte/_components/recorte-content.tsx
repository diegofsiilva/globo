"use client";

/** Tela 06 — Recorte: a população afetada, declarada e ajustável. */

import { useMemo, useRef, useState, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";

import { adjustments } from "../_mocks/scenario";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScreenFrame } from "../../_components/screen-frame";
import { normalizeQueryFailure } from "@/lib/operational-state";
import { fetchEvents, type ApiEvent } from "@/lib/events/api";
import { fetchCrosstab, fetchSessionTimeline, type CrosstabCell } from "../_lib/api-source";
import { useScopeFilters } from "../../_lib/scope-filters";
import { recorteStyles as styles } from "./recorte.styles";

/** Dimensões que realmente existem em `gold.v_feature_bucket`. */
const DIMENSION_X = "entity";
const DIMENSION_Y = "hora_brt";
const SAMPLE_COLUMNS = ["Hora", "Modelo", "SO", "Evento", "Erro"];

type HeatmapCellValue = { sessions: number; errorRate: number | null };

/** Declara o recorte afetado e mede o efeito de cada ajuste sobre ele. */
export function RecorteContent() {
  const [hour, setHour] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const sessionTriggerRef = useRef<HTMLButtonElement | null>(null);

  // Escopo em branco por padrão: os filtros da barra começam em "todos" e só
  // recortam a consulta depois que a pessoa escolhe um valor.
  // O eixo `entity` só representa dispositivo dentro desta fonte. Sem o
  // recorte inicial, o heatmap misturava pods, vhosts e aparelhos.
  const scopeFilters = useScopeFilters({ source: "youbora_device" });
  const scope = scopeFilters.scope;

  // Sessões e taxa são métricas com unidades distintas. `error_rate_pct` já
  // chega em percentual; dividi-la por sessões novamente gerava os 0% falsos.
  const totalQuery = useQuery({
    queryKey: ["recorte", "crosstab", "total", scope],
    queryFn: ({ signal }) =>
      fetchCrosstab(
        {
          dimensionX: DIMENSION_X,
          dimensionY: DIMENSION_Y,
          metric: "sessions",
          limit: 1000,
          scope,
        },
        signal,
      ),
    refetchInterval: 30_000,
  });
  const errorQuery = useQuery({
    queryKey: ["recorte", "crosstab", "error", scope],
    queryFn: ({ signal }) =>
      fetchCrosstab(
        {
          dimensionX: DIMENSION_X,
          dimensionY: DIMENSION_Y,
          metric: "error_rate_pct",
          limit: 1000,
          scope,
        },
        signal,
      ),
    refetchInterval: 30_000,
  });
  const eventsQuery = useQuery({
    queryKey: ["recorte", "events", scope],
    queryFn: ({ signal }) => fetchEvents({ eventName: "error", scope }, signal),
    refetchInterval: 30_000,
  });
  const sessionQuery = useQuery({
    queryKey: ["recorte", "session", selectedSessionId],
    queryFn: ({ signal }) => fetchSessionTimeline(selectedSessionId as string, signal),
    enabled: Boolean(selectedSessionId),
  });

  const { hours, families, cellValues, scaleMax, trueMax } = useMemo(
    () => buildHeatmap(totalQuery.data?.cells ?? [], errorQuery.data?.cells ?? []),
    [totalQuery.data, errorQuery.data],
  );
  const activeHour = hour ?? hours[0] ?? null;
  const ranking = useMemo(
    () =>
      families
        .map((family) => ({ family, rate: rateOf(cellValues, family, activeHour) }))
        .sort((a, b) => (b.rate ?? -1) - (a.rate ?? -1)),
    [families, cellValues, activeHour],
  );

  const samples = (eventsQuery.data?.items ?? []).slice(0, 20);

  // Soma das sessões nas células devolvidas e taxa geral ponderada pelo volume.
  // "% do tráfego" do mock original foi removida porque não há esse contrato.
  const totalEvents = sumCells(totalQuery.data?.cells);
  const errorShare = weightedErrorRate(cellValues);

  const primary = totalQuery;
  const operationalState = primary.isLoading
    ? "loading"
    : primary.isError && !primary.data
      ? "error"
      : primary.isError && primary.data
        ? "stale"
        : primary.isFetching && primary.data
          ? "refreshing"
          : primary.data && families.length === 0
            ? "empty"
            : "ready";

  return (
    <ScreenFrame
      filters={scopeFilters.screenFilters}
      onFilterChange={scopeFilters.onFilterChange}
      onClearFilters={scopeFilters.count ? scopeFilters.clear : undefined}
      scopeFilterCount={scopeFilters.count}
      scopeSummary={scopeSummaryText(totalEvents, errorShare, hours.length)}
      operational={{
        state: operationalState,
        title: "Recorte afetado",
        scope: scopeSummaryText(totalEvents, errorShare, hours.length),
        failure: primary.error
          ? normalizeQueryFailure(
              primary.error,
              primary.dataUpdatedAt ? new Date(primary.dataUpdatedAt).toLocaleTimeString("pt-BR") : undefined,
            )
          : undefined,
        onRetry: () => {
          totalQuery.refetch();
          errorQuery.refetch();
        },
      }}
    >
      <header className={styles.heading}>
        <p>Recorte afetado · definição explícita</p>
        {/* O título é o próprio escopo declarado na barra. Sem filtro ativo ele
            diz isso com todas as letras, em vez de fingir um recorte. */}
        <h1>
          {scopeFilters.count
            ? scopeFilters.active.map((filter) => filter.value).join(" · ")
            : "Todo o tráfego"}
        </h1>
        <div className={styles.metrics}>
          <div>
            <strong>{totalEvents.toLocaleString("pt-BR")}</strong>
            <span>sessões nas células do recorte</span>
          </div>
          <div>
            <strong>{errorShare === null ? "—" : `${errorShare.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}</strong>
            <span>taxa de erro ponderada</span>
          </div>
          <div>
            <strong>{hours.length || "—"}</strong>
            <span>horas BRT no recorte</span>
          </div>
        </div>
      </header>

      <div className={styles.grid}>
        <div>
          <div className={styles.heatmapHead}>
            <h2 className={styles.sectionLabel}>
              Taxa de erro por dispositivo × hora BRT
            </h2>
            {families.length > 0 && (
              <p className={styles.heatLegend}>
                <span className="sr-only">
                  A cor de cada célula indica a taxa de erro relativa à maior célula da grade.
                </span>
                <span aria-hidden="true">0%</span>
                <i
                  aria-hidden="true"
                  style={{
                    background:
                      "linear-gradient(90deg, color-mix(in srgb, var(--primary) 8%, var(--surface)), var(--primary))",
                  }}
                />
                <span aria-hidden="true">
                  {scaleMax > 0
                    ? `${trueMax > scaleMax ? "≥ " : ""}${scaleMax.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
                    : "0%"}
                </span>
              </p>
            )}
          </div>
          {families.length > 0 && (
            <>
              <div className={`${styles.heatmapScroller} hidden md:block`} aria-label="Taxa de erro por dispositivo e hora BRT">
                <div
                  className={styles.heatmap}
                  style={{
                    gridTemplateColumns: `152px repeat(${hours.length}, minmax(40px, 1fr))`,
                    minWidth: 152 + hours.length * 40,
                  }}
                >
                  <div />
                  {hours.map((hourBrt) => (
                    <b key={hourBrt} style={{ lineHeight: 1.3 }}>
                      {hourBrt}h
                    </b>
                  ))}
                  {families.map((family) => (
                    <HeatmapRow
                      key={family}
                      family={family}
                      hours={hours}
                      cellValues={cellValues}
                      scaleMax={scaleMax}
                    />
                  ))}
                </div>
              </div>
              <div className="grid gap-4 md:hidden">
                <div>
                  <label className="mb-2 block font-mono text-xs uppercase tracking-wider text-muted-foreground" id="mobile-hour-label">Hora BRT</label>
                  <Select value={activeHour ?? undefined} onValueChange={setHour}>
                    <SelectTrigger className="w-full" aria-labelledby="mobile-hour-label"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {hours.map((item) => (
                        <SelectItem value={item} key={item}>
                          {item}h
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <ol className="divide-y divide-border border-y border-border">
                  {ranking.map((item, index) => (
                    <li className="flex min-h-14 items-center justify-between gap-4 py-3" key={item.family}>
                      <span className="min-w-0 break-words"><b className="mr-2 font-mono text-muted-foreground">{index + 1}</b>{item.family}</span>
                      <strong className={clsx("flex shrink-0 items-center gap-2 font-mono tabular-nums", index === 0 && "text-critical")}>
                        {item.rate !== null && (
                          <i
                            className={styles.heatSwatch}
                            style={{
                              background: `color-mix(in srgb, var(--primary) ${heatMix(item.rate, scaleMax)}%, var(--surface))`,
                            }}
                            aria-hidden="true"
                          />
                        )}
                        {item.rate === null ? "sem dado" : `${item.rate.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}
                      </strong>
                    </li>
                  ))}
                </ol>
              </div>
            </>
          )}
        </div>

        <aside className={styles.adjustments}>
          <h2>Ajustar o recorte</h2>
          <p>
            Efeito previsto de cada ajuste sobre a especificidade do sinal. Estes cenários são
            informativos e não executam ações.
          </p>
          {/* Sem rota: é simulação what-if, não faz parte do MVP do backend.
              Continua 100% mock, de propósito. */}
          {adjustments.map((adjustment) => (
            <article className={styles.adjustment} key={adjustment.title}>
              <strong>{adjustment.title}</strong>
              <span className={clsx(adjustment.critical && styles.gain)}>
                {adjustment.result}
              </span>
            </article>
          ))}
        </aside>
      </div>

      <section className={styles.samples}>
        <h2 className={styles.sectionLabel}>Amostra de sessões no recorte</h2>
        {eventsQuery.isLoading && <p className={styles.sectionLabel}>Carregando amostra…</p>}
        {eventsQuery.isError && !eventsQuery.data && (
          <p className={styles.sectionLabel}>Não foi possível carregar a amostra de eventos.</p>
        )}
        {samples.length > 0 && (
          <>
            <Table className="table-fixed" containerClassName="hidden md:block">
              <TableHeader>
                <TableRow>
                  {SAMPLE_COLUMNS.map((column, index) => (
                    <TableHead
                      className={clsx(index === 0 && "w-24", index === 2 && "w-32", index === 3 && "w-28")}
                      key={column}
                    >
                      {column}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {samples.map((event) => (
                  <TableRow key={event.event_id}>
                    <TableCell className="font-mono text-xs text-muted-foreground">{formatTime(event.occurred_at)}</TableCell>
                    <TableCell className="break-words font-mono text-xs">{event.device_model ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{event.device_os ?? "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{event.event_name}</TableCell>
                    <TableCell className="break-all font-mono text-xs font-semibold text-primary">
                      <button
                        type="button"
                        className="min-h-11 text-left underline-offset-4 hover:underline"
                        onClick={(clickEvent) => {
                          sessionTriggerRef.current = clickEvent.currentTarget;
                          setSelectedSessionId(event.session_id);
                        }}
                      >
                        {errorSummary(event)}
                      </button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="divide-y divide-border border-y border-border md:hidden">
              {samples.map((event) => (
                <article className="grid gap-3 py-5" key={event.event_id}>
                  <div className="flex items-start justify-between gap-3">
                    <div><p className="font-semibold">{event.device_model ?? "—"}</p><p className="mt-1 font-mono text-xs text-muted-foreground">{event.device_os ?? "—"} · {formatTime(event.occurred_at)}</p></div>
                    <Badge variant={event.event_name === "error" ? "destructive" : "outline"}>{event.event_name}</Badge>
                  </div>
                  <p className="break-all font-mono text-xs">{errorSummary(event)}</p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={(clickEvent) => {
                      sessionTriggerRef.current = clickEvent.currentTarget;
                      setSelectedSessionId(event.session_id);
                    }}
                  >
                    Abrir sessão
                  </Button>
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      <SessionDetail
        sessionId={selectedSessionId}
        data={sessionQuery.data}
        loading={sessionQuery.isLoading}
        onClose={() => setSelectedSessionId(null)}
        returnFocusRef={sessionTriggerRef}
      />
    </ScreenFrame>
  );
}

function SessionDetail({
  sessionId,
  data,
  loading,
  onClose,
  returnFocusRef,
}: {
  sessionId: string | null;
  data: ReturnType<typeof useQuery>["data"];
  loading: boolean;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
}) {
  const session = data as
    | {
        session_id: string;
        events: ApiEvent[];
        summary: {
          device?: { manufacturer?: string | null; model?: string | null; os?: string | null };
          app?: { target?: string | null; version?: string | null };
        };
      }
    | undefined;

  return (
    <Sheet open={Boolean(sessionId)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="overflow-y-auto sm:max-w-lg"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocusRef.current?.focus();
        }}
      >
        {loading && !session && <p>Carregando sessão…</p>}
        {session && (
          <>
            <SheetHeader>
              <SheetTitle>Sessão {session.session_id}</SheetTitle>
              <SheetDescription>
                {session.summary.device?.model ?? "—"} · {session.summary.device?.os ?? "—"}
              </SheetDescription>
            </SheetHeader>
            <div className="grid gap-6 px-4 pb-8">
              <dl className="grid grid-cols-2 gap-px border border-border bg-border text-sm">
                {[
                  ["Modelo", session.summary.device?.model ?? "—"],
                  ["Sistema", session.summary.device?.os ?? "—"],
                  ["Fabricante", session.summary.device?.manufacturer ?? "—"],
                  ["App", session.summary.app?.version ?? session.summary.app?.target ?? "—"],
                ].map(([label, value]) => (
                  <div className="bg-background p-3" key={label}><dt className="font-mono text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-words font-semibold">{value}</dd></div>
                ))}
              </dl>
              <section>
                <h3 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">Cronologia de eventos</h3>
                <ol className="mt-3 border-l border-border pl-4">
                  {session.events.map((event) => (
                    <li className="relative grid gap-1 border-b border-border py-4 before:absolute before:-left-[21px] before:top-5 before:size-2 before:bg-info" key={event.event_id}>
                      <div className="flex flex-wrap items-center gap-2"><time className="font-mono text-xs text-muted-foreground">{formatTime(event.occurred_at)}</time><Badge variant={event.event_name === "error" ? "destructive" : "outline"}>{event.event_name}</Badge></div>
                      <p className="break-words text-sm">{errorSummary(event)}</p>
                    </li>
                  ))}
                </ol>
              </section>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

function HeatmapRow({
  family,
  hours,
  cellValues,
  scaleMax,
}: {
  family: string;
  hours: string[];
  cellValues: Map<string, HeatmapCellValue>;
  scaleMax: number;
}) {
  return (
    <>
      <strong title={family}>{family}</strong>
      {hours.map((hourBrt) => {
        const cell = cellValues.get(key(family, hourBrt));
        const rate = cell?.errorRate ?? null;
        const sessions = cell?.sessions ?? 0;
        const mix = heatMix(rate, scaleMax);
        const ink = mix >= 72;
        return (
          <span
            key={`${family}-${hourBrt}`}
            className={clsx(
              ink && (mix >= 88 ? styles.heatInkMax : styles.heatInk),
              rate === null && "text-muted-foreground",
            )}
            style={{
              background:
                rate === null
                  ? "var(--secondary)"
                  : `color-mix(in srgb, var(--primary) ${mix}%, var(--surface))`,
            }}
            aria-label={cellAriaLabel(family, hourBrt, rate, sessions)}
          >
            <span>{rate === null ? "—" : `${rate.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}</span>
          </span>
        );
      })}
    </>
  );
}

/** Junta as células de sessões e taxa numa grade única. */
function buildHeatmap(totalCells: CrosstabCell[], errorCells: CrosstabCell[]) {
  const cellValues = new Map<string, HeatmapCellValue>();
  for (const cell of totalCells) {
    cellValues.set(key(cell.x, cell.y), { sessions: cell.count, errorRate: null });
  }
  for (const cell of errorCells) {
    const existing = cellValues.get(key(cell.x, cell.y));
    if (existing) existing.errorRate = cell.count;
    else cellValues.set(key(cell.x, cell.y), { sessions: 0, errorRate: cell.count });
  }

  const families = Array.from(new Set(totalCells.map((cell) => cell.x))).sort();
  const hours = Array.from(new Set(totalCells.map((cell) => cell.y))).sort(
    (a, b) => Number(a) - Number(b),
  );
  const scaleMax = robustScaleMax(cellValues);
  let trueMax = 0;
  for (const cell of cellValues.values()) {
    if (cell.errorRate !== null && cell.errorRate > trueMax) trueMax = cell.errorRate;
  }
  return { families, hours, cellValues, scaleMax, trueMax };
}

/** P95 das taxas positivas: um 50% isolado não comprime o restante da grade. */
function robustScaleMax(cellValues: Map<string, HeatmapCellValue>): number {
  const rates = Array.from(cellValues.values())
    .map((cell) => cell.errorRate)
    .filter((rate): rate is number => rate !== null && rate > 0)
    .sort((a, b) => a - b);
  if (rates.length === 0) return 0;
  const index = Math.min(rates.length - 1, Math.ceil(rates.length * 0.95) - 1);
  return rates[Math.max(0, index)] ?? 0;
}

/** Mix de `--primary` na célula: raiz para o meio da escala não virar um degrau. */
function heatMix(rate: number | null, scaleMax: number): number {
  if (rate === null) return 0;
  if (scaleMax <= 0) return 10;
  return Math.min(100, 10 + Math.sqrt(Math.max(0, rate) / scaleMax) * 90);
}

function cellAriaLabel(family: string, hourBrt: string, rate: number | null, sessions: number): string {
  const where = `${family}, ${hourBrt}h BRT`;
  if (rate === null) return `${where}: sem dado`;
  const rateText = `${rate.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  if (sessions <= 0) return `${where}: ${rateText}`;
  return `${where}: ${rateText} em ${sessions.toLocaleString("pt-BR")} sessões`;
}

function key(x: string, y: string): string {
  return JSON.stringify([x, y]);
}

function rateOf(cellValues: Map<string, HeatmapCellValue>, family: string, hourBrt: string | null): number | null {
  if (!hourBrt) return null;
  return cellValues.get(key(family, hourBrt))?.errorRate ?? null;
}

/** Média ponderada pela quantidade de sessões de cada célula. */
function weightedErrorRate(cellValues: Map<string, HeatmapCellValue>): number | null {
  let sessions = 0;
  let estimatedErrors = 0;
  for (const cell of cellValues.values()) {
    if (cell.sessions <= 0 || cell.errorRate === null) continue;
    sessions += cell.sessions;
    estimatedErrors += cell.sessions * (cell.errorRate / 100);
  }
  return sessions > 0 ? (estimatedErrors / sessions) * 100 : null;
}

function sumCells(cells: CrosstabCell[] | undefined): number {
  return (cells ?? []).reduce((total, cell) => total + cell.count, 0);
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function errorSummary(event: ApiEvent): string {
  const attributes = event.attributes as Record<string, unknown>;
  const name = attributes?.["error_name"];
  const message = attributes?.["error_message"];
  if (typeof name === "string" && name) return name;
  if (typeof message === "string" && message) return message;
  return event.event_name;
}

function scopeSummaryText(totalEvents: number, errorShare: number | null, hourCount: number): string {
  const share = errorShare === null ? "sem dado" : `${errorShare.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  return `${totalEvents.toLocaleString("pt-BR")} sessões · ${share} de erro · ${hourCount || "—"} horas BRT`;
}
