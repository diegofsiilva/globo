"use client";

/** Tela 06 — Recorte: a população afetada, declarada e ajustável. */

import { useMemo, useRef, useState, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";

import { adjustments, cutScope } from "../_mocks/scenario";
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
import { regionOf } from "@/lib/uf-regions";
import { fetchCrosstab, fetchSessionTimeline, type CrosstabCell } from "../_lib/api-source";
import { recorteStyles as styles } from "./recorte.styles";

/** Duas dimensões do heatmap. `uf` é código de UF real (ex.: "RJ"), não o
 * nome de região do mock antigo ("Nordeste") -- a série gold/silver não tem
 * granularidade de região NA AGREGAÇÃO (não dá pra pedir "erros por
 * Nordeste" ao crosstab). A coluna mostra UF, que é o dado real, com a
 * região (mapeamento estático, ver lib/uf-regions.ts) como contexto ao lado. */
const DIMENSION_X = "device_model";
const DIMENSION_Y = "uf";
const SAMPLE_COLUMNS = ["Hora", "Modelo", "SO", "Evento", "Erro"];

type HeatmapCellValue = { total: number; errors: number };

/** Declara o recorte afetado e mede o efeito de cada ajuste sobre ele. */
export function RecorteContent() {
  const [region, setRegion] = useState<string | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const sessionTriggerRef = useRef<HTMLButtonElement | null>(null);

  // Contagem, não taxa: /metrics/crosstab devolve count por célula. A taxa de
  // erro por (device_model, uf) sai de DUAS chamadas -- total e só erro --
  // divididas no cliente. Célula sem denominador vira "sem dado", não 0%.
  const totalQuery = useQuery({
    queryKey: ["recorte", "crosstab", "total"],
    queryFn: ({ signal }) => fetchCrosstab({ dimensionX: DIMENSION_X, dimensionY: DIMENSION_Y }, signal),
    refetchInterval: 30_000,
  });
  const errorQuery = useQuery({
    queryKey: ["recorte", "crosstab", "error"],
    queryFn: ({ signal }) =>
      fetchCrosstab({ dimensionX: DIMENSION_X, dimensionY: DIMENSION_Y, eventName: "error" }, signal),
    refetchInterval: 30_000,
  });
  const eventsQuery = useQuery({
    queryKey: ["recorte", "events"],
    queryFn: ({ signal }) => fetchEvents({ eventName: "error" }, signal),
    refetchInterval: 30_000,
  });
  const sessionQuery = useQuery({
    queryKey: ["recorte", "session", selectedSessionId],
    queryFn: ({ signal }) => fetchSessionTimeline(selectedSessionId as string, signal),
    enabled: Boolean(selectedSessionId),
  });

  const { regions, families, cellValues } = useMemo(
    () => buildHeatmap(totalQuery.data?.cells ?? [], errorQuery.data?.cells ?? []),
    [totalQuery.data, errorQuery.data],
  );
  const activeRegion = region ?? regions[0] ?? null;
  const regionIndex = activeRegion ? regions.indexOf(activeRegion) : -1;
  const ranking = useMemo(
    () =>
      families
        .map((family) => ({ family, rate: rateOf(cellValues, family, activeRegion) }))
        .sort((a, b) => (b.rate ?? -1) - (a.rate ?? -1)),
    [families, cellValues, activeRegion],
  );

  const samples = (eventsQuery.data?.items ?? []).slice(0, 20);

  // Proxy de sessões: soma das células do crosstab total. É contagem de
  // EVENTOS agrupados por (device_model, uf), não sessão distinta -- o
  // crosstab não tem essa granularidade. "% do tráfego" do mock original foi
  // removida: exigiria uma chamada extra sem nenhum filtro de escopo como
  // linha de base, que não faz parte deste recorte.
  const totalEvents = sumCells(totalQuery.data?.cells);
  const totalErrors = sumCells(errorQuery.data?.cells);
  const errorShare = totalEvents > 0 ? (totalErrors / totalEvents) * 100 : null;

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
      filters={cutScope.map((chip) => ({ ...chip, options: [chip.value] }))}
      scopeSummary={scopeSummaryText(totalEvents, errorShare, regions.length)}
      operational={{
        state: operationalState,
        title: "Recorte afetado",
        scope: scopeSummaryText(totalEvents, errorShare, regions.length),
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
        {/* Título estático: não há rota que devolva um resumo textual do
            escopo ativo -- ver relatório de integração. */}
        <h1>{cutScope.map((chip) => chip.value).join(" · ")}</h1>
        <div className={styles.metrics}>
          <div>
            <strong>{totalEvents.toLocaleString("pt-BR")}</strong>
            <span>eventos no recorte (proxy de sessões)</span>
          </div>
          <div>
            <strong>{errorShare === null ? "—" : `${errorShare.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}</strong>
            <span>dos eventos são erro</span>
          </div>
          <div>
            <strong>{regions.length || "—"}</strong>
            <span>UFs no recorte</span>
          </div>
        </div>
      </header>

      <div className={styles.grid}>
        <div>
          <h2 className={styles.sectionLabel}>
            Taxa de erro por modelo de dispositivo × UF
          </h2>
          {families.length > 0 && (
            <>
              <div className={`${styles.heatmapScroller} hidden md:block`} aria-label="Taxa de erro por modelo de dispositivo e UF">
                <div className={styles.heatmap} style={{ gridTemplateColumns: `auto repeat(${regions.length}, 1fr)` }}>
                  <div />
                  {regions.map((uf) => (
                    <b key={uf} title={regionOf(uf) ?? undefined} style={{ lineHeight: 1.3 }}>
                      {uf}
                      {regionOf(uf) && <small style={{ display: "block" }}>{regionOf(uf)}</small>}
                    </b>
                  ))}
                  {families.map((family) => (
                    <HeatmapRow
                      key={family}
                      family={family}
                      regions={regions}
                      cellValues={cellValues}
                    />
                  ))}
                </div>
              </div>
              <div className="grid gap-4 md:hidden">
                <div>
                  <label className="mb-2 block font-mono text-xs uppercase tracking-wider text-muted-foreground" id="mobile-region-label">UF</label>
                  <Select value={activeRegion ?? undefined} onValueChange={setRegion}>
                    <SelectTrigger className="w-full" aria-labelledby="mobile-region-label"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {regions.map((item) => (
                        <SelectItem value={item} key={item}>
                          {item}
                          {regionOf(item) ? ` · ${regionOf(item)}` : ""}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <ol className="divide-y divide-border border-y border-border">
                  {ranking.map((item, index) => (
                    <li className="flex min-h-14 items-center justify-between gap-4 py-3" key={item.family}>
                      <span className="min-w-0 break-words"><b className="mr-2 font-mono text-muted-foreground">{index + 1}</b>{item.family}</span>
                      <strong className={clsx("shrink-0 font-mono", index === 0 && "text-critical")}>
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
  regions,
  cellValues,
}: {
  family: string;
  regions: string[];
  cellValues: Map<string, HeatmapCellValue>;
}) {
  return (
    <>
      <strong>{family}</strong>
      {regions.map((uf) => {
        const rate = rateOf(cellValues, family, uf);
        const region = regionOf(uf);
        return (
          <span
            key={`${family}-${uf}`}
            aria-label={`${family}, ${uf}${region ? ` (${region})` : ""}: ${rate === null ? "sem dado" : `${rate.toFixed(1)}%`}`}
          >
            <span>{rate === null ? "—" : `${rate.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}</span>
          </span>
        );
      })}
    </>
  );
}

/** Junta as células total/erro numa grade única e calcula a taxa por par. */
function buildHeatmap(totalCells: CrosstabCell[], errorCells: CrosstabCell[]) {
  const cellValues = new Map<string, HeatmapCellValue>();
  for (const cell of totalCells) {
    cellValues.set(key(cell.x, cell.y), { total: cell.count, errors: 0 });
  }
  for (const cell of errorCells) {
    const existing = cellValues.get(key(cell.x, cell.y));
    if (existing) existing.errors = cell.count;
    else cellValues.set(key(cell.x, cell.y), { total: 0, errors: cell.count });
  }

  const families = Array.from(new Set(totalCells.map((cell) => cell.x))).sort();
  const regions = Array.from(new Set(totalCells.map((cell) => cell.y))).sort();
  return { families, regions, cellValues };
}

function key(x: string, y: string): string {
  return `${x} ${y}`;
}

function rateOf(cellValues: Map<string, HeatmapCellValue>, family: string, region: string | null): number | null {
  if (!region) return null;
  const cell = cellValues.get(key(family, region));
  if (!cell || cell.total === 0) return null;
  return (cell.errors / cell.total) * 100;
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

function scopeSummaryText(totalEvents: number, errorShare: number | null, ufCount: number): string {
  const share = errorShare === null ? "sem dado" : `${errorShare.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
  return `${totalEvents.toLocaleString("pt-BR")} eventos · ${share} de erro · ${ufCount || "—"} UFs`;
}
