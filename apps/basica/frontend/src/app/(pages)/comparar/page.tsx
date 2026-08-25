"use client";

/** Tela 03 — Comparar: a janela atual contra uma referência histórica. */

import { useMemo, useState } from "react";
import { ScreenFrame, type ScreenPeriod } from "@/components/screen-frame";
import {
  chart,
  changes,
  compareScope,
  metrics,
  references,
  scopeSummary,
  type ReferenceId,
} from "@/mocks/comparar";
import styles from "./comparar.module.css";

/** A partir de quantos desvios-padrão o desvio deixa de ser variação normal. */
const SIGNIFICANT_SIGMA = 2;

/** Compara a janela atual com quatro referências de sazonalidade. */
export default function CompararPage() {
  const [period, setPeriod] = useState<ScreenPeriod>("30 min");
  const [reference, setReference] = useState<ReferenceId>("semana");

  const selected = references.find((item) => item.id === reference) ?? references[1];
  const chartMax = useMemo(() => Math.max(...chart.map((bucket) => bucket.now)), []);
  const sigmaMax = useMemo(
    () => Math.max(...metrics.map((metric) => metric.references[reference].sigma)),
    [reference],
  );

  return (
    <ScreenFrame
      period={period}
      onPeriodChange={setPeriod}
      filters={compareScope.map((chip) => ({ ...chip, options: [chip.value] }))}
      scopeSummary={scopeSummary}
    >
      <header className={styles.heading}>
        <h1>Agora contra o passado</h1>
        <p>Mesmo escopo, mesma métrica, janela deslocada no tempo.</p>
      </header>

      {/* Quatro escalas de sazonalidade. Num evento programado o correto é
          comparar contra outro pico, não contra a média. */}
      <div className={styles.references} role="group" aria-label="Referência de comparação">
        {references.map((item) => (
          <button
            className={styles.reference}
            key={item.id}
            type="button"
            aria-pressed={item.id === reference}
            onClick={() => setReference(item.id)}
          >
            <strong>{item.label}</strong>
            <span>{item.detail}</span>
          </button>
        ))}
      </div>

      <div className={styles.body}>
        <section aria-labelledby="chart-title">
          <div className={styles.chartHeader}>
            <h2 id="chart-title">Falha de início de play (video_view · start error)</h2>
            <span>%, bucket de 1 min</span>
          </div>

          <div className={styles.chart}>
            {chart.map((bucket) => (
              <div className={styles.bucket} key={bucket.hour}>
                <i
                  className={`${styles.bar} ${bucket.outside ? styles.outside : ""}`}
                  style={{ height: `${(bucket.now / chartMax) * 100}%` }}
                  title={`${bucket.hour} · ${bucket.now.toLocaleString("pt-BR")}%`}
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
        </section>

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

      <section className={styles.table} aria-label="Métricas comparadas">
        <div className={styles.head}>
          <span>métrica</span>
          <span>agora</span>
          <span>{selected.column}</span>
          <span>Δ</span>
          <span>significância</span>
        </div>
        {metrics.map((metric) => {
          const comparison = metric.references[reference];
          const significant = comparison.sigma >= SIGNIFICANT_SIGMA;

          return (
            <div className={styles.row} key={metric.label}>
              <b>{metric.label}</b>
              <span>{metric.now}</span>
              <span>{comparison.value}</span>
              <span className={`${styles.delta} ${significant ? styles.deltaHot : ""}`}>
                {comparison.delta}
              </span>
              <span className={styles.significance}>
                <span className={styles.meter}>
                  <i
                    className={significant ? styles.hot : undefined}
                    style={{ width: `${meterWidth(comparison.sigma, sigmaMax)}%` }}
                  />
                </span>
                <span className={styles.sigma}>
                  {comparison.sigma.toLocaleString("pt-BR", { minimumFractionDigits: 1 })}σ
                </span>
              </span>
            </div>
          );
        })}
      </section>
    </ScreenFrame>
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
