"use client";

/** Moldura compartilhada pelas telas operacionais. */

import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { screenFrameStyles as styles } from "./screen-frame.styles";

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
  /** Período controlado quando ele também define a consulta da tela. */
  /** `null` mantém todos os atalhos desmarcados numa janela livre. */
  period?: ScreenPeriod | null;
  onPeriodChange?: (period: ScreenPeriod) => void;
  filters?: readonly ScreenFilter[];
  onFilterChange?: (key: string, value: string) => void;
  onClearFilters?: () => void;
  /** Controles de escopo específicos, como chips removíveis da exploração. */
  scopeContent?: ReactNode;
  /** Volumetria do recorte, à direita da barra de escopo. */
  scopeSummary?: string;
};

/**
 * Preenche os slots de controles, escopo e conteúdo do layout operacional.
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
  scopeContent,
  scopeSummary,
}: ScreenFrameProps) {
  const clock = useClock();
  const [internalPeriod, setInternalPeriod] = useState<ScreenPeriod>("30 min");
  const selectedPeriod = period === null ? "" : (period ?? internalPeriod);
  const changePeriod = onPeriodChange ?? setInternalPeriod;
  // Sem filtro nem volumetria a barra de escopo seria uma faixa vazia com a
  // palavra "Escopo" -- some até a tela ter o que declarar ali.
  const showScope =
    filters.length > 0 || Boolean(scopeContent) || Boolean(scopeSummary) || Boolean(onClearFilters);

  return (
    <div className={styles.page}>
      <div
        className={styles.topControls}
        data-operations-slot="controls"
        aria-label="Atualização e período"
      >
        <p className={styles.liveStatus}>
          <span aria-hidden="true" />
          Ao vivo · {clock}
        </p>
        <ToggleGroup
          type="single"
          value={selectedPeriod}
          onValueChange={(value) => value && changePeriod(value as ScreenPeriod)}
          aria-label="Período analisado"
          className={styles.periods}
        >
          {SCREEN_PERIODS.map((value) => (
            <ToggleGroupItem key={value} value={value}>
              {value}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {showScope && (
        <section
          className={styles.scopeBar}
          data-operations-slot="scope"
          aria-label="Filtros do recorte"
        >
          <span className={styles.scopeLabel}>Escopo</span>
          <div className={styles.scopeControls}>
            {scopeContent}
            <div className={styles.filterList}>
              {filters.map((filter) => (
                <div className={styles.filter} key={filter.key}>
                  <span id={`screen-filter-${filter.key}`}>{filter.label}</span>
                  <Select
                    name={filter.key}
                    value={filter.value}
                    onValueChange={(value) => onFilterChange?.(filter.key, value)}
                  >
                    <SelectTrigger size="sm" aria-labelledby={`screen-filter-${filter.key}`}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">todos</SelectItem>
                      {filter.options.map((option) => (
                        <SelectItem value={option} key={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>
          </div>
          <div className={styles.scopeMeta}>
            {scopeSummary && <span>{scopeSummary}</span>}
            {onClearFilters && (
              <Button type="button" variant="ghost" size="sm" onClick={onClearFilters}>
                limpar
              </Button>
            )}
          </div>
        </section>
      )}

      <div className={styles.content} data-operations-slot="content">
        {children}
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
