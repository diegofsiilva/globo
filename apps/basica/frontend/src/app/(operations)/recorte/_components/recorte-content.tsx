"use client";

/** Tela 06 — Recorte: a população afetada, declarada e ajustável. */

import { useMemo, useRef, useState, type RefObject } from "react";

import {
  adjustments,
  cutDefinition,
  heatmap,
  heatmapRegions,
  sampleColumns,
  samples,
  type SessionSample,
} from "../_mocks/scenario";
import clsx from "clsx";
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
import { recorteStyles as styles } from "./recorte.styles";

/** Índice da coluna e da linha que concentram o erro do cenário. */
const hottest = { row: 0, column: 1 };

/** Declara o recorte afetado e mede o efeito de cada ajuste sobre ele. */
export function RecorteContent() {
  const [region, setRegion] = useState("Nordeste");
  const [selectedSession, setSelectedSession] = useState<SessionSample | null>(null);
  const sessionTriggerRef = useRef<HTMLButtonElement | null>(null);
  const regionIndex = heatmapRegions.indexOf(region);
  const ranking = useMemo(
    () => heatmap
      .map((row) => ({ family: row.family, rate: row.rates[Math.max(0, regionIndex)] }))
      .sort((a, b) => Number.parseFloat(b.rate.replace(",", ".")) - Number.parseFloat(a.rate.replace(",", "."))),
    [regionIndex],
  );

  return (
    <>
      <header className={styles.heading}>
        <p>Recorte afetado · definição explícita</p>
        <h1>{cutDefinition.title}</h1>
        {/* A relação entre tráfego e erros é o número que separa "problema
            concentrado num segmento" de "degradação geral da plataforma". */}
        <div className={styles.metrics}>
          {cutDefinition.metrics.map((metric) => (
            <div key={metric.label}>
              <strong>{metric.value}</strong>
              <span>{metric.label}</span>
            </div>
          ))}
        </div>
      </header>

      <div className={styles.grid}>
        <div>
          <h2 className={styles.sectionLabel}>
            Taxa de erro por família de dispositivo × região
          </h2>
          <div className={`${styles.heatmapScroller} hidden md:block`} aria-label="Taxa de erro por família de dispositivo e região">
            <div className={styles.heatmap}>
              <div />
              {heatmapRegions.map((region) => (
                <b key={region}>{region}</b>
              ))}
              {heatmap.map((row, rowIndex) => (
                <HeatmapRow
                  key={row.family}
                  family={row.family}
                  rates={row.rates}
                  rowIndex={rowIndex}
                />
              ))}
            </div>
          </div>
          <div className="grid gap-4 md:hidden">
            <div>
              <label className="mb-2 block font-mono text-xs uppercase tracking-wider text-muted-foreground" id="mobile-region-label">Região</label>
              <Select value={region} onValueChange={setRegion}>
                <SelectTrigger className="w-full" aria-labelledby="mobile-region-label"><SelectValue /></SelectTrigger>
                <SelectContent>{heatmapRegions.map((item) => <SelectItem value={item} key={item}>{item}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <ol className="divide-y divide-border border-y border-border">
              {ranking.map((item, index) => (
                <li className="flex min-h-14 items-center justify-between gap-4 py-3" key={item.family}>
                  <span className="min-w-0 break-words"><b className="mr-2 font-mono text-muted-foreground">{index + 1}</b>{item.family}</span>
                  <strong className={clsx("shrink-0 font-mono", index === 0 && "text-critical")}>{item.rate}</strong>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <aside className={styles.adjustments}>
          <h2>Ajustar o recorte</h2>
          <p>
            Efeito previsto de cada ajuste sobre a especificidade do sinal. Estes cenários são
            informativos e não executam ações.
          </p>
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
        <Table className="table-fixed" containerClassName="hidden md:block">
          <TableHeader>
            <TableRow>
              {sampleColumns.map((column, index) => (
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
            {samples.map((sample) => (
              <TableRow key={sample.id}>
                <TableCell className="font-mono text-xs text-muted-foreground">{sample.observedAt}</TableCell>
                <TableCell className="break-words font-mono text-xs">{sample.device.model}</TableCell>
                <TableCell className="font-mono text-xs">{sample.device.os}</TableCell>
                <TableCell className="font-mono text-xs">{sample.summaryEvent}</TableCell>
                <TableCell className="break-all font-mono text-xs font-semibold text-primary">
                  <button type="button" className="min-h-11 text-left underline-offset-4 hover:underline" onClick={(event) => { sessionTriggerRef.current = event.currentTarget; setSelectedSession(sample); }}>{sample.summary}</button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="divide-y divide-border border-y border-border md:hidden">
          {samples.map((sample) => (
            <article className="grid gap-3 py-5" key={sample.id}>
              <div className="flex items-start justify-between gap-3">
                <div><p className="font-semibold">{sample.device.model}</p><p className="mt-1 font-mono text-xs text-muted-foreground">{sample.device.os} · {sample.observedAt}</p></div>
                <Badge variant={sample.summaryEvent === "error" ? "destructive" : "outline"}>{sample.summaryEvent}</Badge>
              </div>
              <p className="break-all font-mono text-xs">{sample.summary}</p>
              <Button type="button" variant="outline" onClick={(event) => { sessionTriggerRef.current = event.currentTarget; setSelectedSession(sample); }}>Abrir sessão</Button>
            </article>
          ))}
        </div>
      </section>

      <SessionDetail session={selectedSession} onClose={() => setSelectedSession(null)} returnFocusRef={sessionTriggerRef} />
    </>
  );
}

function SessionDetail({
  session,
  onClose,
  returnFocusRef,
}: {
  session: SessionSample | null;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
}) {
  return (
    <Sheet open={Boolean(session)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="overflow-y-auto sm:max-w-lg"
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          returnFocusRef.current?.focus();
        }}
      >
        {session && (
          <>
            <SheetHeader>
              <SheetTitle>Sessão {session.id}</SheetTitle>
              <SheetDescription>{session.device.model} · {session.device.os}</SheetDescription>
            </SheetHeader>
            <div className="grid gap-6 px-4 pb-8">
              <dl className="grid grid-cols-2 gap-px border border-border bg-border text-sm">
                {[["Modelo", session.device.model], ["Sistema", session.device.os], ["Região", session.device.region], ["App", session.device.app]].map(([label, value]) => (
                  <div className="bg-background p-3" key={label}><dt className="font-mono text-xs text-muted-foreground">{label}</dt><dd className="mt-1 break-words font-semibold">{value}</dd></div>
                ))}
              </dl>
              <section>
                <h3 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">Cronologia de eventos</h3>
                <ol className="mt-3 border-l border-border pl-4">
                  {session.events.map((event) => (
                    <li className="relative grid gap-1 border-b border-border py-4 before:absolute before:-left-[21px] before:top-5 before:size-2 before:bg-info" key={`${event.at}-${event.kind}`}>
                      <div className="flex flex-wrap items-center gap-2"><time className="font-mono text-xs text-muted-foreground">{event.at}</time><Badge variant={event.kind === "error" ? "destructive" : "outline"}>{event.kind}</Badge></div>
                      <p className="break-words text-sm">{event.detail}</p>
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

/**
 * Renderiza a linha do heatmap direto na grade, sem elemento intermediário.
 *
 * O grid do heatmap é uma grade só: envolver a linha num `div` quebraria o
 * alinhamento das colunas, então o rótulo e as células saem soltos.
 * @returns Rótulo da família seguido de uma célula por região.
 */
function HeatmapRow({
  family,
  rates,
  rowIndex,
}: {
  family: string;
  rates: string[];
  rowIndex: number;
}) {
  return (
    <>
      <strong>{family}</strong>
      {rates.map((rate, columnIndex) => {
        const isHottest = rowIndex === hottest.row && columnIndex === hottest.column;
        return (
          <span
            key={`${family}-${heatmapRegions[columnIndex]}`}
            aria-label={`${family}, ${heatmapRegions[columnIndex]}: ${rate}${isHottest ? ", maior concentração do recorte" : ""}`}
            className={clsx(
              isHottest && styles.hottest,
              rowIndex === hottest.row && columnIndex !== hottest.column && styles.hot,
            )}
          >
            <span>{rate}</span>
            {isHottest && <small>pico</small>}
          </span>
        );
      })}
    </>
  );
}
