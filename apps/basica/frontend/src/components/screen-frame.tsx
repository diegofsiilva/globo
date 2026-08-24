"use client";

/** Moldura compartilhada pelas telas operacionais. */

import { useEffect, useState, type ReactNode } from "react";
import { OperationsNavigation } from "@/components/operations-navigation";
import styles from "./screen-frame.module.css";

export const SCREEN_PERIODS = ["15 min", "30 min", "3 h", "24 h"] as const;

export type ScreenPeriod = (typeof SCREEN_PERIODS)[number];

/** Filtro exibido na barra de escopo. */
export type ScreenFilter = {
  /** Chave devolvida ao callback de mudança. */
  key: string;
  /** Rótulo da dimensão, ex.: "plataforma". */
  label: string;
  /** Valor selecionado, ou "all" para todos. */
  value: string;
  options: readonly string[];
};

type ScreenFrameProps = {
  children: ReactNode;
  /** Período selecionado. A tela é dona do estado porque ele define a consulta. */
  period: ScreenPeriod;
  onPeriodChange: (period: ScreenPeriod) => void;
  filters?: readonly ScreenFilter[];
  onFilterChange?: (key: string, value: string) => void;
  onClearFilters?: () => void;
  /** Volumetria do recorte, à direita da barra de escopo. */
  scopeSummary?: string;
};

/**
 * Monta o topo, a barra de escopo e a navegação em volta do conteúdo da tela.
 * @param children Conteúdo específico da tela.
 * @returns Estrutura comum das telas operacionais.
 */
export function ScreenFrame({
  children,
  period,
  onPeriodChange,
  filters = [],
  onFilterChange,
  onClearFilters,
  scopeSummary,
}: ScreenFrameProps) {
  const clock = useClock();
  // Sem filtro nem volumetria a barra de escopo seria uma faixa vazia com a
  // palavra "Escopo" -- some até a tela ter o que declarar ali.
  const showScope =
    filters.length > 0 || Boolean(scopeSummary) || Boolean(onClearFilters);

  return (
    <div className={styles.page}>
      <div className={styles.topControls} aria-label="Atualização e período">
        <p className={styles.liveStatus}>
          <span aria-hidden="true" />
          Ao vivo · {clock}
        </p>
        <div className={styles.periods} aria-label="Período analisado">
          {SCREEN_PERIODS.map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={period === value}
              onClick={() => onPeriodChange(value)}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      {showScope && (
        <section className={styles.scopeBar} aria-label="Filtros do recorte">
          <span className={styles.scopeLabel}>Escopo</span>
          <div className={styles.filterList}>
            {filters.map((filter) => (
              <label className={styles.filter} key={filter.key}>
                <span>{filter.label}</span>
                <select
                  aria-label={`Filtrar por ${filter.label}`}
                  value={filter.value}
                  onChange={(event) =>
                    onFilterChange?.(filter.key, event.target.value)
                  }
                >
                  <option value="all">todos</option>
                  {filter.options.map((option) => (
                    <option value={option} key={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <div className={styles.scopeMeta}>
            {scopeSummary && <span>{scopeSummary}</span>}
            {onClearFilters && (
              <button type="button" onClick={onClearFilters}>
                limpar
              </button>
            )}
          </div>
        </section>
      )}

      <div className={styles.workspace}>
        <OperationsNavigation />
        <main className={styles.content} id="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}

/**
 * Mantém a hora corrente, começando só depois da hidratação.
 *
 * Renderizar a hora no HTML exportado geraria divergência entre o que o S3
 * serve e o que o browser calcula no primeiro render.
 * @returns Hora formatada, ou marcador enquanto o relógio não iniciou.
 */
function useClock(): string {
  const [clock, setClock] = useState("--:--:--");

  useEffect(() => {
    // O primeiro acerto vai para a fila de tarefas em vez de rodar no corpo do
    // efeito: escrever estado ali encadeia renders e o lint barra.
    const firstTick = window.setTimeout(() => {
      setClock(new Date().toLocaleTimeString("pt-BR"));
    }, 0);
    const timer = window.setInterval(() => {
      setClock(new Date().toLocaleTimeString("pt-BR"));
    }, 1_000);

    return () => {
      window.clearTimeout(firstTick);
      window.clearInterval(timer);
    };
  }, []);

  return clock;
}
