/** Tela 06 — Recorte: a população afetada, declarada e ajustável. */

import {
  adjustments,
  cutDefinition,
  heatmap,
  heatmapRegions,
  sampleColumns,
  samples,
} from "../_mocks/scenario";
import styles from "../recorte.module.css";

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
            O agente mede o efeito de cada ajuste sobre a especificidade do sinal antes de você
            clicar.
          </p>
          {adjustments.map((adjustment) => (
            <button className={styles.adjustment} type="button" key={adjustment.title}>
              <strong>{adjustment.title}</strong>
              <span className={adjustment.critical ? styles.gain : undefined}>
                {adjustment.result}
              </span>
            </button>
          ))}
        </aside>
      </div>

      <section className={styles.samples}>
        <h2 className={styles.sectionLabel}>Amostra de sessões no recorte</h2>
        <div className={styles.sampleHead}>
          {sampleColumns.map((column) => (
            <span key={column}>{column}</span>
          ))}
        </div>
        {samples.map((row) => (
          <div className={styles.sampleRow} key={row.join("-")}>
            {row.map((cell, index) => (
              <span key={cell} className={index === 4 ? styles.sampleError : undefined}>
                {cell}
              </span>
            ))}
          </div>
        ))}
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
      {rates.map((rate, columnIndex) => (
        <span
          key={`${family}-${heatmapRegions[columnIndex]}`}
          className={
            rowIndex === hottest.row && columnIndex === hottest.column
              ? styles.hottest
              : rowIndex === hottest.row
                ? styles.hot
                : undefined
          }
        >
          {rate}
        </span>
      ))}
    </>
  );
}
