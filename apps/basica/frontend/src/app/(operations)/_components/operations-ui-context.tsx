"use client";

import { createContext, Suspense, useContext, useEffect, useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { usePathname, useSearchParams } from "next/navigation";

export const SCREEN_PERIODS = ["15 min", "30 min", "3 h", "24 h"] as const;
export type ScreenPeriod = (typeof SCREEN_PERIODS)[number];

export const DEMO_STATES = [
  "ready",
  "loading",
  "refreshing",
  "empty",
  "partial",
  "stale",
  "error",
] as const;

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
