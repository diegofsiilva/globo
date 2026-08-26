/** Tela 06 — Recorte: a população afetada, declarada e ajustável. */

import {
  adjustments,
  cutDefinition,
  heatmap,
  heatmapRegions,
  sampleColumns,
  samples,
} from "../_mocks/scenario";
import clsx from "clsx";
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
          <div
            className={styles.heatmapScroller}
            tabIndex={0}
            role="region"
            aria-label="Taxa de erro por família de dispositivo e região"
          >
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
        <Table className="min-w-[780px] table-fixed">
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
            {samples.map((row) => (
              <TableRow key={row.join("-")}>
                {row.map((cell, index) => (
                  <TableCell
                    key={`${row[0]}-${index}`}
                    className={clsx(
                      "font-mono text-[10px]",
                      index === 0 && "text-muted-foreground",
                      index === 4 && "font-semibold text-primary",
                    )}
                  >
                    {cell}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </>
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
