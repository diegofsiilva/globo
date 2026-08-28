/** Filtros de escopo compartilhados pelas telas de investigação.
 *
 * O escopo começa VAZIO e só é restringido quando a pessoa adiciona um filtro:
 * pré-selecionar o primeiro valor de cada faceta produzia um recorte
 * arbitrário (e quase sempre sem resultado) toda vez que a tela abria. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchFacets, type EventScope } from "@/lib/events/query";
import type { ScreenFilter } from "../_components/screen-frame";

/** Valor do item "todos" do `Select` de escopo: significa campo sem recorte. */
export const ALL_SCOPE_VALUES = "all";

/** Campos exibidos como chips de escopo, com o `field` de `/api/v1/series/facets`.
 *
 * Trocados junto com a fonte: plataforma/fabricante/região/app eram colunas de
 * evento por sessão e vinham vazias (ou com lixo, como `device_os = NetRange`).
 * Estes quatro são dimensões reais da série agregada. */
export const scopeFilterDefs = [
  { id: "source", label: "fonte", field: "source" },
  { id: "entity", label: "entidade", field: "entity" },
  { id: "metric", label: "métrica", field: "metric" },
  { id: "match", label: "com jogo", field: "tem_jogo" },
] as const;

/** Um chip de escopo já resolvido: o campo, o valor escolhido e as opções. */
export type ScopeFilter = {
  id: string;
  label: string;
  field: string;
  /** Valor escolhido pela pessoa; vazio enquanto as facetas carregam. */
  value: string;
  /** Todos os valores possíveis do campo, para troca dentro do próprio chip. */
  options: string[];
};

/**
 * Tudo que uma tela precisa para desenhar e operar a barra de escopo.
 *
 * `scope` é o recorte pronto para virar query string; `count` é quantos campos
 * de fato restringem a consulta, e não quantos chips existem — é o que a moldura
 * usa para dizer "3 filtros ativos" sem contar os que estão em "todos".
 */
export type ScopeFiltersState = {
  active: ScopeFilter[];
  scope: EventScope;
  count: number;
  isLoading: boolean;
  /** Pronto para o prop `filters` da moldura, com "todos" no que não recorta. */
  screenFilters: ScreenFilter[];
  onFilterChange: (id: string, value: string) => void;
  clear: () => void;
};

/** Estado dos chips de escopo mais o objeto de filtros pronto para a API.
 *
 * `initialScope` só é usado quando a própria visualização exige uma fonte para
 * que sua dimensão tenha significado (por exemplo, dispositivo no Recorte).
 */
export function useScopeFilters(initialScope: EventScope = {}): ScopeFiltersState {
  const [selection, setSelection] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      scopeFilterDefs.flatMap((filter) => {
        const value = initialScope[filter.field];
        return value ? [[filter.id, value]] : [];
      }),
    ),
  );

  const facetsQuery = useQuery({
    queryKey: ["facets", "scope"],
    queryFn: ({ signal }) => fetchFacets(scopeFilterDefs.map((filter) => filter.field), signal),
    staleTime: 5 * 60_000,
  });

  const filters: ScopeFilter[] = useMemo(
    () =>
      scopeFilterDefs.map((filter) => ({
        ...filter,
        value: selection[filter.id] ?? "",
        options: facetsQuery.data?.facets[filter.field] ?? [],
      })),
    [facetsQuery.data, selection],
  );

  const active = filters.filter((filter) => Boolean(selection[filter.id]));

  const scope: EventScope = useMemo(() => {
    const result: Record<string, string> = {};
    for (const filter of scopeFilterDefs) {
      const value = selection[filter.id];
      if (value) result[filter.field] = value;
    }
    return result;
  }, [selection]);

  const onFilterChange = useCallback((id: string, value: string) => {
    setSelection((current) => {
      const next = { ...current };
      if (value === ALL_SCOPE_VALUES) delete next[id];
      else next[id] = value;
      return next;
    });
  }, []);

  const clear = useCallback(() => setSelection({}), []);

  const screenFilters: ScreenFilter[] = filters.map((filter) => ({
    key: filter.id,
    label: filter.label,
    value: filter.value || ALL_SCOPE_VALUES,
    options: filter.options,
  }));

  return {
    active,
    scope,
    count: active.length,
    isLoading: facetsQuery.isLoading,
    screenFilters,
    onFilterChange,
    clear,
  };
}
