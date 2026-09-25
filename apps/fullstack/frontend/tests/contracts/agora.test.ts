import { afterEach, describe, expect, test, vi } from "vitest";

import { QuerySourceError } from "@/lib/operational-state";
import {
  fetchSignals,
  toSignalDeviation,
  type SignalItem,
} from "@/app/(operations)/agora/_lib/signals-source";

const SIGNAL: SignalItem = {
  id: "signal-1",
  source: "prometheus",
  entity: "playback-api",
  metric: "error_rate_pct",
  title: "Taxa de erro acima do baseline",
  current_value: 12,
  baseline: 4,
  stddev: 2,
  multiplier: 3,
  z: 4,
  threshold_z: 3,
  threshold_value: 10,
  severity: "critical",
  consecutive_buckets_over_threshold: 2,
  detected_at: "2026-07-14T11:45:00.000Z",
  time_since_detection_seconds: 900,
  sessions_impacted: 321,
  direction: "subindo",
  trend: [4, 8, 12],
};

describe("contrato da tela Agora", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("[TA-02] apresenta um sinal real no contrato visual da tela", () => {
    const signal = toSignalDeviation(SIGNAL);

    expect(signal).toMatchObject({
      id: "signal-1",
      source: "prometheus",
      metric: "error_rate_pct",
      severity: "critical",
      current: "12",
      baseline: "4",
      delta: "+8",
      sessions: "321",
      threshold: "10 (z ≥ 3)",
      scope: "playback-api",
      relatedPaths: {
        timeline: "/timeline?sinal=signal-1",
        cut: "/recorte?sinal=signal-1",
      },
    });
    expect(signal.trend).toEqual([4, 19, 34]);
  });

  test("[TA-03] classifica timeout do backend como falha repetível", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 504 })));

    await expect(fetchSignals()).rejects.toMatchObject({
      kind: "timeout",
      reference: "ARG-SIGNALS-HTTP-504",
      retryable: true,
    } satisfies Partial<QuerySourceError>);
  });
});
