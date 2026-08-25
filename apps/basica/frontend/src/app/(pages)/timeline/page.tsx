"use client";

/** Tela 05 — Timeline: seis fontes sobre um eixo temporal único. */

import { useState } from "react";
import { ScreenFrame, type ScreenPeriod } from "@/components/screen-frame";
import {
  chronology,
  correlationWindow,
  scopeSummary,
  timeAxis,
  timelineRows,
  timelineScope,
} from "@/mocks/timeline";
import styles from "./timeline.module.css";

/** Reconstrói a sequência do incidente com as fontes que a originaram. */
export default function TimelinePage() {
  const [period, setPeriod] = useState<ScreenPeriod>("30 min");

  return (
    <ScreenFrame
      period={period}
      onPeriodChange={setPeriod}
      filters={timelineScope.map((chip) => ({ ...chip, options: [chip.value] }))}
      scopeSummary={scopeSummary}
    >
      <header className={styles.heading}>
        <h1>Timeline única do incidente</h1>
        <p>Seis fontes em silos, um único eixo de tempo. Janela de correlação destacada.</p>
      </header>

      <div className={styles.chart}>
        <div className={styles.axis}>
          {timeAxis.map((hour) => (
            <span key={hour}>{hour}</span>
          ))}
        </div>
        <div className={styles.band} aria-hidden="true" />
        {timelineRows.map((row) => (
          <div className={styles.row} key={row.label}>
            <div className={styles.source}>
              <strong>{row.label}</strong>
              <span>{row.source}</span>
            </div>
            <div className={styles.track}>
              <div
                className={`${styles.event} ${styles[row.kind]}`}
                style={{ left: `${row.start}%`, width: row.width ? `${row.width}%` : "auto" }}
              >
                <strong>{row.event}</strong>
                <span>{row.detail}</span>
                {row.width > 0 && <i />}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.lower}>
        {/* A cronologia repete os mesmos fatos em texto, cada linha atribuída à
            sua fonte: é o que mantém a afirmação rastreável quando alguém
            questionar de onde saiu a sequência. */}
        <section className={styles.chronology}>
          <h2>Cronologia reconstruída</h2>
          {chronology.map((entry) => (
            <div className={styles.chronologyRow} key={entry.hour}>
              <time className={entry.accent ? styles.accent : undefined}>{entry.hour}</time>
              <b>{entry.source}</b>
              <p>{entry.description}</p>
            </div>
          ))}
        </section>

        <aside className={styles.card} aria-label="Janela de correlação">
          <small>Janela de correlação</small>
          <h2>{correlationWindow.label}</h2>
          <p>{correlationWindow.description}</p>
          <hr />
          {correlationWindow.metrics.map((metric) => (
            <div className={styles.metric} key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          ))}
        </aside>
      </div>
    </ScreenFrame>
  );
}
