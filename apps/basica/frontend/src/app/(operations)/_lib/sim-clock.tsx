"use client";

/** Relógio virtual compartilhado pelas telas operacionais.
 *
 * O dataset é reproduzido pelo simulador e pode estar pausado ou em uma data
 * diferente do relógio do navegador. Toda janela relativa precisa terminar em
 * `sim_now`, nunca em `new Date()`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { QuerySourceError } from "@/lib/operational-state";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const CLOCK_REFRESH_MS = 30_000;

type ClockPayload = {
  sim_now: string;
  speed: number;
  updated_at: string;
};

type ClockSnapshot = {
  simNow: Date;
  speed: number;
  updatedAt: Date;
  receivedAt: number;
};

type SimClockValue = {
  snapshot: ClockSnapshot | null;
  isLoading: boolean;
  isFetching: boolean;
  error: Error | null;
  refetch: () => void;
};

const SimClockContext = createContext<SimClockValue | null>(null);

/** Mantém uma única leitura periódica de `/api/v1/clock` por rota operacional. */
export function SimClockProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<ClockSnapshot | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isFetching, setIsFetching] = useState(true);
  const [refreshToken, setRefreshToken] = useState(0);

  const refetch = useCallback(() => setRefreshToken((current) => current + 1), []);

  useEffect(() => {
    const controller = new AbortController();

    async function loadClock() {
      setIsFetching(true);
      try {
        const next = await fetchClock(controller.signal);
        setSnapshot(next);
        setError(null);
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(caught instanceof Error ? caught : new Error("Falha desconhecida ao ler o relógio."));
      } finally {
        if (!controller.signal.aborted) setIsFetching(false);
      }
    }

    const firstLoad = window.setTimeout(loadClock, 0);
    const timer = window.setInterval(loadClock, CLOCK_REFRESH_MS);
    return () => {
      controller.abort();
      window.clearTimeout(firstLoad);
      window.clearInterval(timer);
    };
  }, [refreshToken]);

  const value = useMemo<SimClockValue>(
    () => ({
      snapshot,
      isLoading: snapshot === null && error === null,
      isFetching,
      error,
      refetch,
    }),
    [error, isFetching, refetch, snapshot],
  );

  return <SimClockContext.Provider value={value}>{children}</SimClockContext.Provider>;
}

/** Lê o presente virtual compartilhado pela moldura operacional. */
export function useSimClock(): SimClockValue {
  const value = useContext(SimClockContext);
  if (!value) throw new Error("useSimClock deve ser usado dentro de SimClockProvider.");
  return value;
}

/** Cria uma janela ISO terminando no instante virtual informado. */
export function windowEndingAt(simNow: Date, minutes: number) {
  return {
    from: new Date(simNow.getTime() - minutes * 60_000).toISOString(),
    to: simNow.toISOString(),
  };
}

/** Projeta o relógio entre duas leituras sem misturá-lo ao relógio de parede. */
export function projectedSimNow(snapshot: ClockSnapshot, browserNow = Date.now()): Date {
  const elapsed = Math.max(0, browserNow - snapshot.receivedAt);
  return new Date(snapshot.simNow.getTime() + elapsed * snapshot.speed);
}

async function fetchClock(signal: AbortSignal): Promise<ClockSnapshot> {
  if (!API_URL) {
    throw new QuerySourceError(
      "NEXT_PUBLIC_API_URL não está configurada no bundle.",
      "invalid-response",
      "ARG-CLOCK-NO-URL",
      false,
    );
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL.replace(/\/$/, "")}/api/v1/clock`, { signal });
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") throw caught;
    throw new QuerySourceError(
      "A conexão com o relógio do simulador está indisponível.",
      "offline",
      "ARG-CLOCK-OFFLINE",
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A leitura do relógio do simulador excedeu o tempo limite."
        : `A API do relógio respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `ARG-CLOCK-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  let payload: ClockPayload;
  try {
    payload = (await response.json()) as ClockPayload;
  } catch {
    throw new QuerySourceError(
      "A API do relógio respondeu em um formato inválido.",
      "invalid-response",
      "ARG-CLOCK-INVALID-JSON",
      false,
    );
  }

  const simNow = new Date(payload.sim_now);
  const updatedAt = new Date(payload.updated_at);
  if (
    !Number.isFinite(simNow.getTime()) ||
    !Number.isFinite(updatedAt.getTime()) ||
    !Number.isFinite(payload.speed)
  ) {
    throw new QuerySourceError(
      "A API do relógio respondeu sem um instante virtual válido.",
      "invalid-response",
      "ARG-CLOCK-INVALID-SHAPE",
      false,
    );
  }

  return { simNow, speed: payload.speed, updatedAt, receivedAt: Date.now() };
}
