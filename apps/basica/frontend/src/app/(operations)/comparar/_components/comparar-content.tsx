"use client";

/** Tela 03 — Comparar: a janela atual contra uma referência histórica. */

import { useMemo, useState } from "react";
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
import {
  chart,
  changes,
  metrics,
  references,
  type ReferenceId,
} from "../_mocks/scenario";
import { compararStyles as styles } from "./comparar.styles";

/** A partir de quantos desvios-padrão o desvio deixa de ser variação normal. */
const SIGNIFICANT_SIGMA = 2;

/** Compara a janela atual com quatro referências de sazonalidade. */
export function CompararContent() {
  const [reference, setReference] = useState<ReferenceId>("semana");

  const selected = references.find((item) => item.id === reference) ?? references[1];
  const chartMax = useMemo(() => Math.max(...chart.map((bucket) => bucket.now)), []);
  const sigmaMax = useMemo(
    () => Math.max(...metrics.map((metric) => metric.references[reference].sigma)),
    [reference],
  );

  return (
    <>
      <header className={styles.heading}>
        <h1>Agora contra o passado</h1>
        <p>Mesmo escopo, mesma métrica, janela deslocada no tempo.</p>
      </header>

      {/* Quatro escalas de sazonalidade. Num evento programado o correto é
          comparar contra outro pico, não contra a média. */}
      <ToggleGroup
        className={styles.references}
        type="single"
        value={reference}
        onValueChange={(value) => value && setReference(value as ReferenceId)}
        aria-label="Referência de comparação"
      >
        {references.map((item) => (
          <ToggleGroupItem
            className={styles.reference}
            key={item.id}
            value={item.id}
            aria-label={`${item.label}: ${item.detail}`}
          >
            <strong>{item.label}</strong>
            <span>{item.detail}</span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>

      <div className={styles.body}>
        <figure aria-labelledby="chart-title">
          <div className={styles.chartHeader}>
            <h2 id="chart-title">Falha de início de play (video_view · start error)</h2>
            <span>%, bucket de 1 min</span>
          </div>

          <div className={styles.chart} aria-hidden="true">
            {chart.map((bucket) => (
              <div className={styles.bucket} key={bucket.hour}>
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

          <div className={styles.axis}>
            <span>{chart[0].hour}</span>
            <span>{chart[Math.floor(chart.length / 3)].hour}</span>
            <span>{chart[Math.floor((chart.length / 3) * 2)].hour}</span>
            <span>{chart[chart.length - 1].hour}</span>
          </div>

          <p className={styles.legend}>
            <span>
              <i aria-hidden="true" />
              agora
            </span>
            <span>
              <i className={styles.line} aria-hidden="true" />
              {selected.column}
            </span>
            <span>
              <i className={styles.hot} aria-hidden="true" />
              fora do envelope histórico
            </span>
          </p>
          <figcaption className="sr-only">
            Série de falha de início por minuto. {chart.map((bucket) =>
              `${bucket.hour}: agora ${bucket.now.toLocaleString("pt-BR")}% e referência ${bucket.reference.toLocaleString("pt-BR")}%${bucket.outside ? ", fora do envelope histórico" : ""}`,
            ).join("; ")}.
          </figcaption>
        </figure>

        <aside className={styles.changes}>
          <h2>O que mudou entre as janelas</h2>
          {changes.map((change) => (
            <article className={styles.change} key={change.hour}>
              <time>{change.hour}</time>
              <p>{change.description}</p>
            </article>
          ))}
        </aside>
      </div>

      <section className={styles.table} aria-labelledby="comparison-table-title">
        <h2 id="comparison-table-title" className="sr-only">Métricas comparadas</h2>
        <Table className="table-fixed" containerClassName="hidden md:block">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[30%]">Métrica</TableHead>
              <TableHead className="text-right">Agora</TableHead>
              <TableHead className="text-right">{selected.column}</TableHead>
              <TableHead className="text-right">Δ</TableHead>
              <TableHead className="w-[28%]">Significância</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {metrics.map((metric) => {
              const comparison = metric.references[reference];
              const significant = comparison.sigma >= SIGNIFICANT_SIGMA;

              return (
                <TableRow key={metric.label}>
                  <TableCell className="font-semibold text-foreground">{metric.label}</TableCell>
                  <TableCell className="text-right font-mono font-semibold">{metric.now}</TableCell>
                  <TableCell className="text-right font-mono text-muted-foreground">{comparison.value}</TableCell>
                  <TableCell className={clsx("text-right font-mono font-semibold", significant && "text-primary")}>
                    {comparison.delta}
                  </TableCell>
                  <TableCell>
                    <span className={styles.significance}>
                      <span className={styles.meter} aria-hidden="true">
                        <i
                          className={clsx(significant && styles.hot)}
                          style={{ width: `${meterWidth(comparison.sigma, sigmaMax)}%` }}
                        />
                      </span>
                      <span className={styles.sigma}>
                        {comparison.sigma.toLocaleString("pt-BR", { minimumFractionDigits: 1 })}σ
                        {significant && <span className="sr-only">, desvio significativo</span>}
                      </span>
                    </span>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <div className="divide-y divide-border border-y border-border md:hidden" aria-label="Métricas comparadas">
          {metrics.map((metric) => {
            const comparison = metric.references[reference];
            const significant = comparison.sigma >= SIGNIFICANT_SIGMA;
            return (
              <article className="grid gap-4 py-5" key={metric.label}>
                <div className="flex items-start justify-between gap-3">
                  <h3 className="break-words font-semibold">{metric.label}</h3>
                  <span className={clsx("shrink-0 border px-2 py-1 font-mono text-xs", significant ? "border-critical text-critical" : "border-border text-muted-foreground")}>
                    {significant ? "Desvio significativo" : "Variação normal"}
                  </span>
                </div>
                <dl className="grid grid-cols-3 gap-3 font-mono text-xs">
                  <div><dt className="text-muted-foreground">Agora</dt><dd className="mt-1 font-semibold">{metric.now}</dd></div>
                  <div><dt className="text-muted-foreground">{selected.column}</dt><dd className="mt-1">{comparison.value}</dd></div>
                  <div><dt className="text-muted-foreground">Variação</dt><dd className={clsx("mt-1 font-semibold", significant && "text-critical")}>{comparison.delta}</dd></div>
                </dl>
                <div className={styles.significance}>
                  <span className={styles.meter} aria-hidden="true"><i className={clsx(significant && styles.hot)} style={{ width: `${meterWidth(comparison.sigma, sigmaMax)}%` }} /></span>
                  <span className={styles.sigma}>{comparison.sigma.toLocaleString("pt-BR", { minimumFractionDigits: 1 })}σ</span>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </>
  );
}

/**
 * Converte desvios-padrão em largura de barra, em escala logarítmica.
 *
 * Linear, 14σ ao lado de 0,2σ deixaria toda a metade de baixo da tabela como
 * um traço invisível, e é justamente ali que está a leitura útil: distinguir
 * 1,2σ (variação normal) de 2,1σ (começo de desvio). O log preserva a ordem e
 * mantém as pequenas legíveis.
 * @param sigma Distância do esperado, em desvios-padrão.
 * @param max Maior sigma da tabela, que ancora a escala.
 * @returns Largura em porcentagem, entre 4 e 100.
 */
function meterWidth(sigma: number, max: number): number {
  if (max <= 0) return 4;
  const scaled = Math.log1p(Math.max(0, sigma)) / Math.log1p(max);
  return Math.max(4, Math.min(100, scaled * 100));
}
