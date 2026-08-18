"use client";

/** Tela 04 — Hipóteses: causas prováveis ranqueadas e decomposição do score. */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/components/sidebar";
import {
  factorStrength,
  fetchHypotheses,
  type DiscardedHypothesis,
  type Hypothesis,
  type HypothesesReport,
} from "@/lib/hypotheses-api";

type Period = "15" | "30" | "180" | "1440";

const PERIODS: Period[] = ["15", "30", "180", "1440"];

// Mesma chave do monitor de eventos: o período é a janela de investigação, não
// uma preferência de tela. Trocá-lo em Agora e voltar ao padrão em Hipóteses
// faria o operador comparar duas janelas diferentes sem perceber.
const PERIOD_STORAGE_KEY = "event-monitor-period";

/** Tons da faixa de fatores, do mais para o menos determinante. */
const FACTOR_SHADES = ["#201e1d", "#575453", "#8f8b8b", "#cfcccc"];

/** @returns Tela de hipóteses com lista ranqueada, descartes e painel do score. */
export function HypothesesScreen() {
  const [period, setPeriod] = useState<Period>("30");
  const [now, setNow] = useState<Date | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // O relógio só começa depois da hidratação: renderizar a hora no HTML estático
  // exportado geraria divergência entre servidor e cliente.
  useEffect(() => {
    const restoreTimer = window.setTimeout(() => {
      const saved = window.localStorage.getItem(PERIOD_STORAGE_KEY);
      if (isPeriod(saved)) setPeriod(saved);
      setNow(new Date());
    }, 0);
    const timer = window.setInterval(() => setNow(new Date()), 1_000);
    return () => {
      window.clearTimeout(restoreTimer);
      window.clearInterval(timer);
    };
  }, []);

  const selectPeriod = (value: Period) => {
    setPeriod(value);
    window.localStorage.setItem(PERIOD_STORAGE_KEY, value);
  };

  const report = useQuery({
    queryKey: ["hypotheses", period],
    queryFn: ({ signal }) => fetchHypotheses(periodWindow(period), signal),
    refetchInterval: 30_000,
  });

  const hypotheses = useMemo(() => report.data?.hypotheses ?? [], [report.data]);
  const selected = hypotheses.find((item) => item.id === selectedId) ?? hypotheses[0] ?? null;

  return (
    <div className="dashboard-shell">
      <div className="top-controls">
        <div className="live">
          <i />
          {report.isFetching ? "Atualizando" : "Ao vivo"} ·{" "}
          {now?.toLocaleTimeString("pt-BR") ?? "--:--:--"}
        </div>
        <div className="period-picker">
          {PERIODS.map((value) => (
            <button
              key={value}
              aria-pressed={period === value}
              onClick={() => selectPeriod(value)}
            >
              {periodLabel(value)}
            </button>
          ))}
        </div>
      </div>

      <ScopeBar report={report.data} />

      <div className="dashboard-body">
        <Sidebar notificationCounts={{ agora: 3, hipoteses: hypotheses.length }} />
        <main className="analysis-area">
          <header className="hypotheses-header">
            <h1>Hipóteses de causa provável</h1>
            {report.data && (
              <p>
                {report.data.generated} geradas · {report.data.discarded} descartadas · janela{" "}
                {report.data.window.label}
              </p>
            )}
          </header>

          {report.isLoading && <p className="empty-state">Consultando o motor de hipóteses…</p>}
          {report.isError && (
            <p className="empty-state error">
              Não foi possível carregar as hipóteses. Tente novamente.
            </p>
          )}

          {report.data && (
            <div className="hypotheses-layout">
              <section className="hypotheses-list" aria-label="Hipóteses ranqueadas">
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
        </main>
      </div>
    </div>
  );
}

/** Renderiza os filtros do recorte e a volumetria analisada. */
function ScopeBar({ report }: { report?: HypothesesReport }) {
  return (
    <div className="scope-bar">
      <span className="scope-label">Escopo</span>
      {report?.scope.map((chip) => (
        <button className="scope-chip" key={chip.id} type="button">
          <span>{chip.label}</span>
          <b>{chip.value}</b>
          <i aria-hidden="true">×</i>
        </button>
      ))}
      <button className="add-filter" type="button">
        + filtro
      </button>
      {report && (
        <p>
          {report.summary.sessions.toLocaleString("pt-BR")} sessões ·{" "}
          {report.summary.trafficShare.toLocaleString("pt-BR", { minimumFractionDigits: 1 })}% do
          tráfego · {report.summary.sources} fontes cruzadas
        </p>
      )}
      <button className="clear-filter" type="button">
        limpar
      </button>
    </div>
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
      className={`hypothesis-item${selected ? " selected" : ""}`}
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
    >
      <strong className="hypothesis-score">{hypothesis.score}</strong>
      <span className="hypothesis-body">
        <span className="hypothesis-kicker">
          Hipótese {rank} · {hypothesis.category}
        </span>
        <span className="hypothesis-title">{hypothesis.title}</span>
        {/* A faixa tem o comprimento total do score e cada segmento vale a
            contribuição do seu fator: a comparação entre hipóteses e a
            composição de cada uma ficam legíveis na mesma marca. */}
        <span className="factor-strip" aria-hidden="true">
          {hypothesis.factors.map((factor, index) => (
            <i
              key={factor.id}
              style={{
                width: `${factor.contribution}%`,
                background: FACTOR_SHADES[index] ?? FACTOR_SHADES[FACTOR_SHADES.length - 1],
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
    <section className="discarded-section">
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
    <aside className="score-panel" aria-label="Composição do score">
      <p className="panel-kicker">Como este score foi calculado</p>
      <h2>{hypothesis.title}</h2>

      <p className="panel-score">
        <strong>{hypothesis.score}</strong>
        <span>
          soma ponderada de {hypothesis.factors.length} fatores, normalizada em 0–100. Confiança{" "}
          {hypothesis.confidence}.
        </span>
      </p>

      <ul className="factor-list">
        {hypothesis.factors.map((factor) => (
          <li key={factor.id}>
            <div className="factor-head">
              <strong>{factor.label}</strong>
              <span>
                peso {factor.weight.toLocaleString("pt-BR", { minimumFractionDigits: 2 })} · contribui{" "}
                {factor.contribution.toLocaleString("pt-BR", { minimumFractionDigits: 1 })} pts
              </span>
            </div>
            <div className="factor-meter">
              <i style={{ width: `${factorStrength(factor) * 100}%` }} />
            </div>
            <p>{factor.rationale}</p>
          </li>
        ))}
      </ul>

      <p className="panel-kicker">Evidências consultadas</p>
      <ul className="evidence-list">
        {hypothesis.evidence.map((item) => (
          <li key={item.source}>
            <b>{item.source}</b>
            <span>{item.detail}</span>
          </li>
        ))}
      </ul>

      {/* As duas ações encadeiam os fluxos: a hipótese viaja na URL para que a
          timeline e o recorte abram já centrados nela. */}
      <div className="panel-actions">
        <Link
          className="action primary"
          href={`/timeline/?hipotese=${hypothesis.id}&t=${encodeURIComponent(hypothesis.timelineAnchor)}`}
        >
          Abrir na timeline
        </Link>
        <Link
          className="action"
          href={`/recorte/?hipotese=${hypothesis.id}&segmento=${encodeURIComponent(hypothesis.segment)}`}
        >
          Ver recorte afetado
        </Link>
      </div>
    </aside>
  );
}

/** Valida valores restaurados como períodos aceitos pela tela. */
function isPeriod(value: string | null): value is Period {
  return PERIODS.some((period) => period === value);
}

/** Retorna o rótulo compacto correspondente ao período. */
function periodLabel(period: Period): string {
  return period === "180" ? "3 h" : period === "1440" ? "24 h" : `${period} min`;
}

/** Retorna a janela ISO correspondente ao período selecionado. */
function periodWindow(period: Period) {
  const to = new Date();
  return {
    from: new Date(to.getTime() - Number(period) * 60_000).toISOString(),
    to: to.toISOString(),
  };
}
