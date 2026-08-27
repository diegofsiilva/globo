/** Tela 05 — Timeline: seis fontes sobre um eixo temporal único. */

import {
  chronology,
  correlationWindow,
  timeAxis,
  timelineRows,
} from "../_mocks/scenario";
import clsx from "clsx";
import { timelineStyles as styles } from "./timeline.styles";

/** Reconstrói a sequência do incidente com as fontes que a originaram. */
export function TimelineContent() {
  return (
    <>
      <header className={styles.heading}>
        <h1>Timeline única do incidente</h1>
        <p>Seis fontes em silos, um único eixo de tempo. Janela de correlação destacada.</p>
      </header>

      <figure
        className={styles.chart}
        aria-labelledby="timeline-chart-caption"
        aria-describedby="timeline-chronology"
      >
        <div aria-hidden="true">
          <div className={styles.axis}>
            {timeAxis.map((hour) => (
              <span key={hour}>{hour}</span>
            ))}
          </div>
          <div className={styles.band} />
          {timelineRows.map((row) => (
            <div className={styles.row} key={row.label}>
              <div className={styles.source}>
                <strong>{row.label}</strong>
                <span>{row.source}</span>
              </div>
              <div className={styles.track}>
                <div
                  className={clsx(styles.event, styles[row.kind])}
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
        <figcaption id="timeline-chart-caption" className="sr-only">
          Eixo temporal correlacionado de seis fontes. A cronologia textual a seguir apresenta os
          mesmos eventos, horários, fontes e detalhes em formato acessível.
        </figcaption>
      </figure>

      <div className={styles.lower}>
        {/* A cronologia repete os mesmos fatos em texto, cada linha atribuída à
            sua fonte: é o que mantém a afirmação rastreável quando alguém
            questionar de onde saiu a sequência. */}
        <section className={styles.chronology} id="timeline-chronology">
          <h2>Cronologia reconstruída</h2>
          {chronology.map((entry) => (
            <div className={styles.chronologyRow} key={entry.hour}>
              <time className={clsx(entry.accent && styles.accent)}>{entry.hour}</time>
              <b>{entry.source}</b>
              <p>{entry.description}</p>
            </div>
          ))}
        </section>

        <aside className={styles.card} aria-label="Janela de correlação">
          <small>Janela de correlação</small>
          <h2 className="text-gradient-emphasis">{correlationWindow.label}</h2>
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
    </>
  );
}
