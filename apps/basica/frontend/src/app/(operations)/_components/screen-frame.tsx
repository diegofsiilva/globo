"use client";

import type { ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { OperationalStateBoundary, type OperationalPresentation } from "./operational-state";
import { ALL_SCOPE_VALUES } from "../_lib/scope-filters";
import { screenFrameStyles as styles } from "./screen-frame.styles";

export { SCREEN_PERIODS, type ScreenPeriod } from "./operations-ui-context";

/**
 * Um seletor da barra de escopo.
 *
 * `value` igual a `ALL_SCOPE_VALUES` significa "sem recorte neste campo" — não é
 * um valor de dado, e a moldura o desconta da contagem de filtros ativos.
 */
export type ScreenFilter = {
  key: string;
  label: string;
  value: string;
  options: readonly string[];
};

type ScreenFrameProps = {
  children: ReactNode;
  filters?: readonly ScreenFilter[];
  onFilterChange?: (key: string, value: string) => void;
  onClearFilters?: () => void;
  scopeContent?: ReactNode;
  scopeSummary?: string;
  scopeFilterCount?: number;
  operational?: OperationalPresentation;
};

/**
 * Moldura comum das seis telas: barra de escopo, resumo e estados operacionais.
 *
 * Existe para que as telas não reimplementem carregamento, vazio, erro e stale
 * cada uma à sua maneira — o operador aprende o vocabulário visual uma vez e ele
 * vale em todas.
 *
 * A barra de escopo só é renderizada quando há algo nela; uma tela sem filtros
 * não ganha um cabeçalho vazio.
 *
 * @param children Conteúdo da tela.
 * @param filters Seletores de escopo.
 * @param onFilterChange Chamado quando um seletor muda.
 * @param onClearFilters Chamado no botão de limpar; a ausência esconde o botão.
 * @param scopeContent Conteúdo extra da barra, quando a tela precisa de mais que
 *   seletores.
 * @param scopeSummary Frase que resume o recorte, exibida ao lado dos filtros.
 * @param scopeFilterCount Quantos filtros de fato restringem; sem valor, usa o
 *   total de seletores.
 * @param operational Estado operacional da consulta principal.
 */
export function ScreenFrame({
  children,
  filters = [],
  onFilterChange,
  onClearFilters,
  scopeContent,
  scopeSummary,
  scopeFilterCount,
  operational = { title: "Consulta operacional" },
}: ScreenFrameProps) {
  const showScope = filters.length > 0 || Boolean(scopeContent) || Boolean(scopeSummary) || Boolean(onClearFilters);

  return (
    <div className={styles.page}>
      {showScope && (
        <>
          <section className={styles.mobileScope} data-operations-slot="scope" aria-label="Filtros do recorte">
            <Sheet>
              <SheetTrigger asChild>
                <Button type="button" variant="outline" className="w-full justify-between">
                  <span>Escopo · {scopeFilterCount ?? filters.length} {(scopeFilterCount ?? filters.length) === 1 ? "filtro" : "filtros"}</span>
                  <SlidersHorizontal aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="overflow-y-auto">
                <SheetHeader>
                  <SheetTitle>Escopo da consulta</SheetTitle>
                  <SheetDescription>Ajuste os filtros aplicados à tela atual.</SheetDescription>
                </SheetHeader>
                <div className="grid gap-5 px-4 pb-6">
                  {scopeContent}
                  <ScopeFilters filters={filters} idPrefix="mobile" onFilterChange={onFilterChange} />
                  {scopeSummary && <p className="font-mono text-xs text-muted-foreground">{scopeSummary}</p>}
                  {onClearFilters && (
                    <Button type="button" variant="outline" onClick={onClearFilters}>Limpar filtros</Button>
                  )}
                </div>
              </SheetContent>
            </Sheet>
          </section>

          <section className={styles.scopeBar} data-operations-slot="scope" aria-label="Filtros do recorte">
            <span className={styles.scopeLabel}>Escopo</span>
            <div className={styles.scopeControls}>
              {scopeContent}
              <ScopeFilters filters={filters} idPrefix="desktop" onFilterChange={onFilterChange} />
            </div>
            <div className={styles.scopeMeta}>
              {scopeSummary && <span>{scopeSummary}</span>}
              {onClearFilters && (
                <Button type="button" variant="ghost" size="sm" onClick={onClearFilters}>limpar</Button>
              )}
            </div>
          </section>
        </>
      )}

      <div className={styles.content} data-operations-slot="content">
        <OperationalStateBoundary presentation={operational}>{children}</OperationalStateBoundary>
      </div>
    </div>
  );
}

function ScopeFilters({
  filters,
  idPrefix,
  onFilterChange,
}: {
  filters: readonly ScreenFilter[];
  idPrefix: string;
  onFilterChange?: (key: string, value: string) => void;
}) {
  return (
    <div className={styles.filterList}>
      {filters.map((filter) => {
        const labelId = `${idPrefix}-screen-filter-${filter.key}`;
        return (
          <div className={styles.filter} key={filter.key}>
            <span id={labelId}>{filter.label}</span>
            <Select
              name={`${idPrefix}-${filter.key}`}
              value={filter.value}
              onValueChange={(value) => onFilterChange?.(filter.key, value)}
            >
              <SelectTrigger size="sm" aria-labelledby={labelId}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_SCOPE_VALUES}>todos</SelectItem>
                {filter.options.map((option) => (
                  <SelectItem value={option} key={option}>{option}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        );
      })}
    </div>
  );
}
