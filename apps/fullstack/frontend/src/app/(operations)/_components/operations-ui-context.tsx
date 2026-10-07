"use client";

import { createContext, Suspense, useContext, useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { usePathname, useSearchParams } from "next/navigation";

/**
 * Períodos oferecidos no seletor da moldura, do mais curto ao mais longo.
 *
 * O teto é 72 h, e não 24 h: quem investiga um incidente chega depois dele, e
 * com 24 h as hipóteses de anteontem não tinham como aparecer na tela. Não vai
 * além porque a Timeline lê seis fontes na janela inteira — 72 h respondem em
 * cerca de 6 s; 7 dias, em mais de 10 s, perto do limite da consulta.
 */
export const SCREEN_PERIODS = ["15 min", "30 min", "3 h", "24 h", "72 h"] as const;
/** Um dos períodos de {@link SCREEN_PERIODS}. */
export type ScreenPeriod = (typeof SCREEN_PERIODS)[number];

/**
 * Estados operacionais que a moldura sabe desenhar.
 *
 * Forçáveis por query string (`?estado=empty`) para demonstrar e revisar cada
 * um sem precisar reproduzir a condição real -- derrubar a API só para ver a
 * tela de erro custaria mais que o valor da revisão.
 */
export const DEMO_STATES = [
  "ready",
  "loading",
  "refreshing",
  "empty",
  "partial",
  "stale",
  "error",
] as const;

/** Um dos estados de {@link DEMO_STATES}. */
export type OperationalState = (typeof DEMO_STATES)[number];

type OperationsUiValue = {
  period: ScreenPeriod | null;
  setPeriod: (period: ScreenPeriod | null) => void;
  demoState: OperationalState | null;
  clearDemoState: () => void;
  hrefWithDemoState: (href: string) => string;
};

const OperationsUiContext = createContext<OperationsUiValue | null>(null);

/** Mantém controles globais estáveis enquanto o usuário percorre as seis rotas. */
export function OperationsUiProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [period, setPeriod] = useState<ScreenPeriod | null>("30 min");
  const [demoState, setDemoState] = useState<OperationalState | null>(null);

  const value = useMemo<OperationsUiValue>(() => ({
    period,
    setPeriod,
    demoState,
    clearDemoState: () => {
      const params = new URLSearchParams(window.location.search);
      params.delete("demoState");
      const query = params.toString();
      setDemoState(null);
      window.history.replaceState(window.history.state, "", query ? `${pathname}?${query}` : pathname);
    },
    hrefWithDemoState: (href) => {
      if (demoState === null) return href;
      const separator = href.includes("?") ? "&" : "?";
      return `${href}${separator}demoState=${demoState}`;
    },
  }), [demoState, pathname, period]);

  return (
    <OperationsUiContext.Provider value={value}>
      {children}
      <Suspense fallback={null}>
        <DemoStateObserver onStateChange={setDemoState} />
      </Suspense>
    </OperationsUiContext.Provider>
  );
}

/**
 * Acessa o estado de interface compartilhado pela moldura.
 *
 * @returns Período selecionado, estado forçado e o helper de link que o
 *   preserva na navegação.
 * @throws Se usado fora de `OperationsUiProvider` -- falhar alto é melhor que
 *   devolver um contexto vazio, que apareceria como período sempre nulo.
 */
export function useOperationsUi(): OperationsUiValue {
  const value = useContext(OperationsUiContext);
  if (!value) throw new Error("useOperationsUi deve ser usado dentro de OperationsUiProvider.");
  return value;
}

function isOperationalState(value: string | null): value is OperationalState {
  return DEMO_STATES.some((state) => state === value);
}

function DemoStateObserver({
  onStateChange,
}: {
  onStateChange: Dispatch<SetStateAction<OperationalState | null>>;
}) {
  const searchParams = useSearchParams();
  const requested = searchParams.get("demoState");

  useEffect(() => {
    const tick = window.setTimeout(() => {
      onStateChange(isOperationalState(requested) ? requested : null);
    }, 0);
    return () => window.clearTimeout(tick);
  }, [onStateChange, requested]);

  return null;
}
