"use client";

/** Tela 05 — Timeline: seis fontes sobre um eixo temporal único. */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ScreenFrame } from "../../_components/screen-frame";
import { useOperationsUi, type ScreenPeriod } from "../../_components/operations-ui-context";
import { useSimClock, windowEndingAt } from "../../_lib/sim-clock";
import { normalizeQueryFailure } from "@/lib/operational-state";
import { fetchTimeline } from "../_lib/http-source";
import {
  formatMoment,
  toChronology,
  toCorrelationWindow,
  toMarker,
  toTimeAxis,
  toTimelineRows,
  windowAround,
} from "../_lib/adapt";
import { timelineStyles as styles } from "./timeline.styles";

/** Minutos de cada período, para converter o rótulo na janela consultada. */
const periodMinutes: Record<ScreenPeriod, number> = {
  "15 min": 15,
  "30 min": 30,
  "3 h": 180,
  "24 h": 1_440,
  "72 h": 4_320,
};

/** Largura, em px, da coluna de rótulos das raias (`row` em timeline.styles). */
const LANE_LABEL_WIDTH = 150;

/** Posiciona um elemento sobre o eixo, descontando a coluna de rótulos. */
function axisOffset(percent: number): string {
  return `calc(${LANE_LABEL_WIDTH}px + (100% - ${LANE_LABEL_WIDTH}px) * ${percent / 100})`;
}

/** Reconstrói a sequência do incidente com as fontes que a originaram. */
export function TimelineContent() {
  const { period: sharedPeriod, hrefWithDemoState } = useOperationsUi();
  const clock = useSimClock();
  const searchParams = useSearchParams();
  const period = sharedPeriod ?? "30 min";

  // "Abrir na timeline", na tela de Hipóteses, manda a hipótese e o instante do
  // efeito na URL. Sem ler os dois, a tela abria sempre na janela que termina
  // agora, e uma hipótese de ontem caía num eixo em que ela não aparece.
  const hypothesisId = searchParams.get("hipotese");
  const anchorParam = searchParams.get("t");
  const anchor = anchorParam && Number.isFinite(new Date(anchorParam).getTime())
    ? new Date(anchorParam)
    : null;

  const currentWindow = clock.snapshot
    ? anchor
      ? windowAround(anchor, clock.snapshot.simNow, periodMinutes[period])
      : windowEndingAt(clock.snapshot.simNow, periodMinutes[period])
    : null;

  const query = useQuery({
    queryKey: ["timeline", period, currentWindow?.from, currentWindow?.to],
    queryFn: ({ signal }) => fetchTimeline(currentWindow!, signal),
    enabled: Boolean(currentWindow),
    refetchInterval: 30_000,
  });

  const response = query.data;
  const timeAxis = response ? toTimeAxis(response) : [];
  const timelineRows = response ? toTimelineRows(response) : [];
  const chronology = response ? toChronology(response) : [];
  const correlationWindow = response ? toCorrelationWindow(response, hypothesisId) : null;
  const marker = response && anchor ? toMarker(response, anchor.toISOString()) : null;
  const scope = response
    ? `janela ${period}${anchor ? ` centrada em ${formatMoment(anchor.getTime())}` : ""} · ${response.lanes.length} fontes`
    : undefined;

  return (
    <ScreenFrame
      scopeSummary={scope}
      operational={{
        state: clock.error && !clock.snapshot
          ? "error"
          : clock.isLoading || query.isLoading
          ? "loading"
          : query.isError && !query.data
            ? "error"
            : query.isError && query.data
              ? "stale"
              : query.isFetching && query.data
                ? "refreshing"
                : response && timelineRows.every((row) => row.width === 0)
                  ? "empty"
                  : "ready",
        title: "Timeline correlacionada",
        scope,
        failure: clock.error
          ? normalizeQueryFailure(clock.error)
          : query.error
            ? normalizeQueryFailure(
                query.error,
                query.dataUpdatedAt ? new Date(query.dataUpdatedAt).toLocaleTimeString("pt-BR") : undefined,
              )
            : undefined,
        onRetry: () => {
          clock.refetch();
          query.refetch();
        },
      }}
    >
      <header className={styles.heading}>
        <h1>Timeline única do incidente</h1>
        <p>Seis fontes em silos, um único eixo de tempo. Janela de correlação destacada.</p>
      </header>

      {anchor && (
        <p className={styles.focus}>
          <span>
            Janela centrada {hypothesisId ? <>na hipótese <strong>#{hypothesisId}</strong></> : "no instante"}
            {" · "}efeito em <strong>{formatMoment(anchor.getTime())}</strong>
          </span>
          <Link href={hrefWithDemoState("/hipoteses")}>Voltar às hipóteses</Link>
          <Link href={hrefWithDemoState("/timeline")}>Ver a janela de agora</Link>
        </p>
      )}

      {response && correlationWindow && (
        <>
          <figure
            className={styles.chart}
            aria-labelledby="timeline-chart-caption"
            aria-describedby="timeline-chronology"
          >
            <div aria-hidden="true">
              <div className={styles.axis}>
                {timeAxis.map((hour, index) => (
                  <span key={`${hour}-${index}`}>{hour}</span>
                ))}
              </div>
              {correlationWindow.band && (
                <div
                  className={styles.band}
                  style={{
                    // O percentual é da JANELA, e o eixo começa depois da
                    // coluna de rótulos: aplicado à largura inteira, o
                    // destaque cobria os nomes das raias e ficava deslocado
                    // em relação aos eventos.
                    left: axisOffset(correlationWindow.band.start),
                    width: `calc((100% - ${LANE_LABEL_WIDTH}px) * ${correlationWindow.band.width / 100})`,
                  }}
                />
              )}
              {marker !== null && (
                <div className={styles.marker} style={{ left: axisOffset(marker) }}>
                  <span>{hypothesisId ? `hipótese #${hypothesisId}` : "instante"}</span>
                </div>
              )}
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
              {chronology.length === 0 && <p>Sem eventos registrados na janela consultada.</p>}
              {chronology.map((entry, index) => (
                <div className={styles.chronologyRow} key={`${entry.hour}-${index}`}>
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
      )}
    </ScreenFrame>
  );
}
