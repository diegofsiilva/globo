"use client";

/** Tela 03 — Comparar: a janela atual contra uma referência histórica. */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScreenFrame, type ScreenPeriod } from "../../_components/screen-frame";
import { useOperationsUi } from "../../_components/operations-ui-context";
import { useSimClock, windowEndingAt } from "../../_lib/sim-clock";
import { normalizeQueryFailure } from "@/lib/operational-state";
import { fetchChanges, fetchTimeseries } from "../_lib/http-source";
import { resolveReference } from "../_lib/comparar-source";
import type { ChartBucket, ReferenceId, WindowChange } from "../_lib/types";
import { compararStyles as styles } from "./comparar.styles";

/** Rótulo e detalhe fixos das quatro referências -- só a JANELA é real. */
const REFERENCE_META: Record<ReferenceId, { label: string; column: string }> = {
  ontem: { label: "Ontem, mesmo horário", column: "ontem" },
  semana: { label: "Semana passada", column: "semana passada" },
  estavel: { label: "Última janela estável", column: "janela estável" },
  pico: { label: "Pico ao vivo anterior", column: "pico anterior" },
};

const periodMinutes: Record<ScreenPeriod, number> = {
  "15 min": 15,
  "30 min": 30,
  "3 h": 180,
  "24 h": 1_440,
};

// `sessions` chega com a latência de 28 h da NPAW e deixa as janelas de 15/30
// min legitimamente vazias. `request_count` é uma contagem recente e existe
// nos dois lados da comparação, sem misturar métricas de unidades diferentes.
const COMPARISON_METRIC = "request_count";

/** Compara a janela atual com quatro referências de sazonalidade. */
export function CompararContent() {
  const { period: sharedPeriod } = useOperationsUi();
  const clock = useSimClock();
  const period = sharedPeriod ?? "30 min";
  const [reference, setReference] = useState<ReferenceId>("semana");

  const windowMinutes = periodMinutes[period];
  const currentWindow = useMemo(
    () => clock.snapshot ? windowEndingAt(clock.snapshot.simNow, windowMinutes) : null,
    [clock.snapshot, windowMinutes],
  );
  const interval = Math.max(5, Math.round(windowMinutes / 30));

  const atual = useQuery({
    queryKey: ["comparar-atual", currentWindow?.from, currentWindow?.to, interval],
    queryFn: ({ signal }) =>
      fetchTimeseries({ ...currentWindow!, interval, metric: COMPARISON_METRIC }, signal),
    enabled: Boolean(currentWindow),
    refetchInterval: 30_000,
  });

  const changesQuery = useQuery({
    queryKey: ["comparar-changes", currentWindow?.from, currentWindow?.to],
    queryFn: ({ signal }) => fetchChanges(currentWindow!.from, currentWindow!.to, signal),
    enabled: Boolean(currentWindow),
    refetchInterval: 30_000,
  });

  const referenciaResolvida = useQuery({
    queryKey: ["comparar-referencia-janela", reference, currentWindow?.from, currentWindow?.to],
    queryFn: ({ signal }) =>
      resolveReference(reference, currentWindow!, signal),
    enabled: Boolean(currentWindow),
  });

  const janelaRef = referenciaResolvida.data;
  const referenciaSerie = useQuery({
    queryKey: ["comparar-referencia-serie", janelaRef?.from, janelaRef?.to, interval],
    queryFn: ({ signal }) =>
      fetchTimeseries(
        { from: janelaRef!.from, to: janelaRef!.to, interval, metric: COMPARISON_METRIC },
        signal,
      ),
    enabled: Boolean(janelaRef?.found),
  });

  const chart = useMemo(
    () => buildChart(atual.data?.buckets, referenciaSerie.data?.buckets),
    [atual.data, referenciaSerie.data],
  );
  const chartMax = useMemo(
    () => Math.max(1, ...chart.map((bucket) => Math.max(bucket.now, bucket.reference))),
    [chart],
  );
  const changes = useMemo(() => mapChanges(changesQuery.data), [changesQuery.data]);

  const nowTotal = atual.data?.total ?? null;
  const refTotal = janelaRef?.found ? (referenciaSerie.data?.total ?? null) : null;
  const delta = nowTotal !== null && refTotal !== null ? nowTotal - refTotal : null;
  const ratio = nowTotal !== null && refTotal !== null && refTotal > 0 ? delta! / refTotal : null;

  const loading = clock.isLoading || atual.isLoading;
  const anyError = Boolean(clock.error) || atual.isError || changesQuery.isError;
  const scopeSummary = nowTotal !== null ? `${nowTotal.toLocaleString("pt-BR")} eventos na janela` : undefined;

  return (
    <ScreenFrame
      scopeSummary={scopeSummary}
      operational={{
        state: loading
          ? "loading"
          : anyError && !atual.data
            ? "error"
            : anyError && atual.data
              ? "stale"
              : atual.isFetching && atual.data
                ? "refreshing"
                : "ready",
        title: "Comparação histórica",
        scope: scopeSummary,
        failure: clock.error
          ? normalizeQueryFailure(clock.error)
          : atual.error
            ? normalizeQueryFailure(
                atual.error,
                atual.dataUpdatedAt ? new Date(atual.dataUpdatedAt).toLocaleTimeString("pt-BR") : undefined,
              )
            : undefined,
        onRetry: () => {
          clock.refetch();
          atual.refetch();
          changesQuery.refetch();
        },
      }}
    >
      <header className={styles.heading}>
        <h1>Agora contra o passado</h1>
        <p>Mesmo escopo, mesma métrica, janela deslocada no tempo.</p>
      </header>

      <ToggleGroup
        className={styles.references}
        type="single"
        value={reference}
        onValueChange={(value) => value && setReference(value as ReferenceId)}
        aria-label="Referência de comparação"
      >
        {(Object.keys(REFERENCE_META) as ReferenceId[]).map((id) => (
          <ToggleGroupItem
            className={styles.reference}
            key={id}
            value={id}
            aria-label={`${REFERENCE_META[id].label}${janelaRef && reference === id ? `: ${janelaRef.detail}` : ""}`}
          >
            <strong>{REFERENCE_META[id].label}</strong>
            <span>{reference === id ? (janelaRef?.detail ?? "carregando…") : ""}</span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      {janelaRef && !janelaRef.found && (
        <p className="mt-3 text-micro text-muted-foreground">
          {REFERENCE_META[reference].label.toLowerCase()}: {janelaRef.detail}. Nenhum dado real
          disponível para essa referência agora.
        </p>
      )}

      <div className={styles.body}>
        <figure aria-labelledby="chart-title">
          <div className={styles.chartHeader}>
            <h2 id="chart-title">Volume de eventos</h2>
            <span>contagem por bucket de {interval} min</span>
          </div>

          <div className={styles.chart} aria-hidden="true">
            {chart.map((bucket, index) => (
              <div className={styles.bucket} key={`${bucket.hour}-${index}`}>
                <i
                  className={clsx(styles.bar, bucket.outside && styles.outside)}
                  style={{ height: `${(bucket.now / chartMax) * 100}%` }}
                />
                <i
                  className={styles.referenceLine}
                  style={{ bottom: `${(bucket.reference / chartMax) * 100}%` }}
                  aria-hidden="true"
                />
              </div>
            ))}
          </div>

          {chart.length > 0 && (
            <div className={styles.axis}>
              <span>{chart[0].hour}</span>
              <span>{chart[Math.floor(chart.length / 3)]?.hour}</span>
              <span>{chart[Math.floor((chart.length / 3) * 2)]?.hour}</span>
              <span>{chart[chart.length - 1].hour}</span>
            </div>
          )}

          <p className={styles.legend}>
            <span>
              <i aria-hidden="true" />
              agora
            </span>
            <span>
              <i className={styles.line} aria-hidden="true" />
              {REFERENCE_META[reference].column}
            </span>
            <span>
              <i className={styles.hot} aria-hidden="true" />
              50%+ acima da referência
            </span>
          </p>
        </figure>

        <aside className={styles.changes}>
          <h2>O que mudou entre as janelas</h2>
          {changes.length === 0 && (
            <p className="text-micro text-muted-foreground">
              Nenhum deploy registrado nesta janela.
            </p>
          )}
          {changes.map((change, index) => (
            <article className={styles.change} key={`${change.hour}-${index}`}>
              <time>{change.hour}</time>
              <p>{change.description}</p>
            </article>
          ))}
          <p className="mt-2 text-micro text-muted-foreground">
            Só cobre deploy (fonte Tsuru) — autoscale e mudança de regra de WAF não têm dado
            discreto neste dataset.
          </p>
        </aside>
      </div>

      <section className={styles.table} aria-labelledby="comparison-table-title">
        <h2 id="comparison-table-title" className="sr-only">Métricas comparadas</h2>
        <Table className="table-fixed" containerClassName="hidden md:block">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[30%]">Métrica</TableHead>
              <TableHead className="text-right">Agora</TableHead>
              <TableHead className="text-right">{REFERENCE_META[reference].column}</TableHead>
              <TableHead className="text-right">Δ</TableHead>
              <TableHead className="w-[28%]">Variação</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell className="font-semibold text-foreground">Volume de eventos</TableCell>
              <TableCell className="text-right font-mono font-semibold">
                {nowTotal?.toLocaleString("pt-BR") ?? "…"}
              </TableCell>
              <TableCell className="text-right font-mono text-muted-foreground">
                {refTotal !== null ? refTotal.toLocaleString("pt-BR") : "—"}
              </TableCell>
              <TableCell
                className={clsx(
                  "text-right font-mono font-semibold",
                  ratio !== null && Math.abs(ratio) >= 0.2 && "text-primary",
                )}
              >
                {delta !== null ? formatSigned(delta) : "—"}
              </TableCell>
              <TableCell>
                {ratio !== null ? (
                  <span className={styles.significance}>
                    <span className={styles.meter} aria-hidden="true">
                      <i
                        className={clsx(Math.abs(ratio) >= 0.2 && styles.hot)}
                        style={{ width: `${Math.min(100, Math.abs(ratio) * 100)}%` }}
                      />
                    </span>
                    <span className={styles.sigma}>{formatPercent(ratio)}</span>
                  </span>
                ) : (
                  <span className="text-micro text-muted-foreground">sem referência</span>
                )}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
        <p className="mt-3 text-micro text-muted-foreground">
          Reduzido a uma métrica real (volume total de eventos na janela): o backend não expõe
          hoje a decomposição por métrica de negócio (falha de play, join time, buffer ratio
          etc.) nem desvio-padrão histórico — não é possível calcular significância estatística
          (σ) sem essa fonte.
        </p>
      </section>
    </ScreenFrame>
  );
}

function buildChart(
  atual: Array<{ bucket: string; count: number }> | undefined,
  referencia: Array<{ bucket: string; count: number }> | undefined,
): ChartBucket[] {
  if (!atual || atual.length === 0) return [];
  return atual.map((bucket, index) => {
    const refBucket = referencia?.[index];
    const now = bucket.count;
    const reference = refBucket?.count ?? 0;
    return {
      hour: formatHour(bucket.bucket),
      now,
      reference,
      outside: reference > 0 ? now > reference * 1.5 : now > 0,
    };
  });
}

function mapChanges(response: { items: Array<{ started_at: string; kind: string | null; target_value: string | null; owner: string | null }> } | undefined): WindowChange[] {
  if (!response) return [];
  return response.items.map((item) => ({
    hour: formatHour(item.started_at),
    description: `${item.kind ?? "Mudança"}${item.target_value ? ` · ${item.target_value}` : ""}${item.owner ? ` (${item.owner})` : ""}`,
  }));
}

function formatHour(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

function formatSigned(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("pt-BR")}`;
}

function formatPercent(ratio: number): string {
  const sign = ratio > 0 ? "+" : "";
  return `${sign}${(ratio * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}
