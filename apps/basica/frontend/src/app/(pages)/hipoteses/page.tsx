"use client";

/** Tela 04 — Hipóteses: causas prováveis ranqueadas e decomposição do score. */

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScreenFrame, type ScreenFilter, type ScreenPeriod } from "@/components/screen-frame";
import {
  factorStrength,
  fetchHypotheses,
  type DiscardedHypothesis,
  type Hypothesis,
  type HypothesesReport,
} from "@/lib/hypotheses/api";
import styles from "./hipoteses.module.css";

/** Minutos de cada período, para converter o rótulo na janela consultada. */
const periodMinutes: Record<ScreenPeriod, number> = {
  "15 min": 15,
  "30 min": 30,
  "3 h": 180,
  "24 h": 1_440,
};

/** Tons da faixa de fatores, do mais para o menos determinante. */
const factorShades = ["#201e1d", "#575453", "#8f8b8b", "#cfcccc"];

/** Causas prováveis do recorte, ranqueadas e com o score decomposto. */
export default function HipotesesPage() {
  const [period, setPeriod] = useState<ScreenPeriod>("30 min");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const report = useQuery({
    queryKey: ["hypotheses", period],
    queryFn: ({ signal }) => fetchHypotheses(periodWindow(period), signal),
    refetchInterval: 30_000,
  });

  const hypotheses = useMemo(() => report.data?.hypotheses ?? [], [report.data]);
  const selected = hypotheses.find((item) => item.id === selectedId) ?? hypotheses[0] ?? null;

  return (
    <ScreenFrame
      period={period}
      onPeriodChange={setPeriod}
      filters={scopeFilters(report.data)}
      scopeSummary={scopeSummary(report.data)}
    >
      <header className={styles.header}>
        <h1>Hipóteses de causa provável</h1>
        {report.data && (
          <p>
            {report.data.generated} geradas · {report.data.discarded} descartadas · janela{" "}
            {report.data.window.label}
          </p>
        )}
      </header>

      {report.isLoading && <p className={styles.state}>Consultando o motor de hipóteses…</p>}
      {report.isError && (
        <p className={`${styles.state} ${styles.error}`}>
          Não foi possível carregar as hipóteses. Tente novamente.
        </p>
      )}

      {report.data && (
        <div className={styles.layout}>
          <section className={styles.list} aria-label="Hipóteses ranqueadas">
            <ol>
              {hypotheses.map((hypothesis, index) => (
                <li key={hypothesis.id}>
                  <HypothesisItem
                    hypothesis={hypothesis}
                    rank={index + 1}
                    selected={hypothesis.id === selected?.id}
                    onSelect={() => setSelectedId(hypothesis.id)}
                  />
                </li>
              ))}
            </ol>
            {/* Mostrar o que foi descartado é o que separa "avaliado e
                rejeitado" de "nunca considerado" -- sem isso o operador não
                consegue distinguir os dois casos. */}
            <DiscardedList items={report.data.discardedHypotheses} />
          </section>

          {selected && <ScorePanel hypothesis={selected} />}
        </div>
      )}
    </ScreenFrame>
  );
}

/** Renderiza uma hipótese ranqueada e comunica a seleção ao callback. */
function HypothesisItem({
  hypothesis,
  rank,
  selected,
  onSelect,
}: {
  hypothesis: Hypothesis;
  rank: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`${styles.item} ${selected ? styles.selected : ""}`}
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
    >
      <strong className={styles.score}>{hypothesis.score}</strong>
      <span className={styles.body}>
        <span className={styles.kicker}>
          Hipótese {rank} · {hypothesis.category}
        </span>
        <span className={styles.title}>{hypothesis.title}</span>
        {/* A faixa tem o comprimento total do score e cada segmento vale a
            contribuição do seu fator: a comparação entre hipóteses e a
            composição de cada uma ficam legíveis na mesma marca. */}
        <span className={styles.strip} aria-hidden="true">
          {hypothesis.factors.map((factor, index) => (
            <i
              key={factor.id}
              style={{
                width: `${factor.contribution}%`,
                background: factorShades[index] ?? factorShades[factorShades.length - 1],
              }}
            />
          ))}
        </span>
      </span>
    </button>
  );
}

/** Renderiza as hipóteses avaliadas e rejeitadas com o motivo do descarte. */
function DiscardedList({ items }: { items: DiscardedHypothesis[] }) {
  if (items.length === 0) return null;

  return (
    <section className={styles.discarded}>
      <p>Descartadas</p>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <b>{String(item.score).padStart(2, "0")}</b>
            <span>
              <strong>{item.title}</strong> — {item.reason}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Renderiza a decomposição do score, as evidências e as ações da hipótese. */
function ScorePanel({ hypothesis }: { hypothesis: Hypothesis }) {
  return (
    <aside className={styles.panel} aria-label="Composição do score">
      <p className={styles.panelKicker}>Como este score foi calculado</p>
      <h2>{hypothesis.title}</h2>

      <p className={styles.panelScore}>
        <strong>{hypothesis.score}</strong>
        <span>
          soma ponderada de {hypothesis.factors.length} fatores, normalizada em 0–100. Confiança{" "}
          {hypothesis.confidence}.
        </span>
      </p>

      <ul className={styles.factors}>
        {hypothesis.factors.map((factor) => (
          <li key={factor.id}>
            <div className={styles.factorHead}>
              <strong>{factor.label}</strong>
              <span>
                peso {factor.weight.toLocaleString("pt-BR", { minimumFractionDigits: 2 })} ·
                contribui{" "}
                {factor.contribution.toLocaleString("pt-BR", { minimumFractionDigits: 1 })} pts
              </span>
            </div>
            <div className={styles.meter}>
              <i style={{ width: `${factorStrength(factor) * 100}%` }} />
            </div>
            <p>{factor.rationale}</p>
          </li>
        ))}
      </ul>

      <p className={styles.panelKicker}>Evidências consultadas</p>
      <ul className={styles.evidence}>
        {hypothesis.evidence.map((item) => (
          <li key={item.source}>
            <b>{item.source}</b>
            <span>{item.detail}</span>
          </li>
        ))}
      </ul>

      {/* As duas ações encadeiam os fluxos: a hipótese viaja na URL para que a
          timeline e o recorte abram já centrados nela. */}
      <div className={styles.actions}>
        <Link
          className={`${styles.action} ${styles.primary}`}
          href={`/timeline?hipotese=${hypothesis.id}&t=${encodeURIComponent(hypothesis.timelineAnchor)}`}
        >
          Abrir na timeline
        </Link>
        <Link
          className={styles.action}
          href={`/recorte?hipotese=${hypothesis.id}&segmento=${encodeURIComponent(hypothesis.segment)}`}
        >
          Ver recorte afetado
        </Link>
      </div>
    </aside>
  );
}

/** Converte os chips do relatório nos filtros exibidos na barra de escopo. */
function scopeFilters(report?: HypothesesReport): ScreenFilter[] {
  return (report?.scope ?? []).map((chip) => ({
    key: chip.id,
    label: chip.label,
    value: chip.value,
    options: [chip.value],
  }));
}

/** Formata a volumetria do recorte exibida à direita da barra de escopo. */
function scopeSummary(report?: HypothesesReport): string | undefined {
  if (!report) return undefined;
  const share = report.summary.trafficShare.toLocaleString("pt-BR", { minimumFractionDigits: 1 });
  return `${report.summary.sessions.toLocaleString("pt-BR")} sessões · ${share}% do tráfego · ${report.summary.sources} fontes cruzadas`;
}

/** Retorna a janela ISO correspondente ao período selecionado. */
function periodWindow(period: ScreenPeriod) {
  const to = new Date();
  return {
    from: new Date(to.getTime() - periodMinutes[period] * 60_000).toISOString(),
    to: to.toISOString(),
  };
}
