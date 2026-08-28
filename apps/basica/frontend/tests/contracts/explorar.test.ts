import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchBreakdown } from "@/app/(operations)/explorar/_lib/api";

describe("contrato HTTP da tela Explorar", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("[TA-01] envia janela e escopo cumulativo para o breakdown", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          dimension: "entity",
          metric: "sessions",
          total: 42,
          groups: [{ key: "LG webOS", value: 42, points: 3, share: 1 }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchBreakdown(
      "entity",
      { from: "2026-07-14T11:00:00.000Z", to: "2026-07-14T12:00:00.000Z" },
      { source: "youbora_device", metric: "sessions", tem_jogo: "true" },
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const endpoint = new URL(String(fetchMock.mock.calls[0][0]));
    expect(endpoint.pathname).toBe("/api/v1/series/breakdown");
    expect(Object.fromEntries(endpoint.searchParams)).toEqual({
      dimension: "entity",
      from: "2026-07-14T11:00:00.000Z",
      to: "2026-07-14T12:00:00.000Z",
      limit: "100",
      source: "youbora_device",
      metric: "sessions",
      tem_jogo: "true",
    });
    expect(result).toEqual({
      dimension: "entity",
      total: 42,
      groups: [{ key: "LG webOS", count: 42, share: 1, average_duration_ms: null }],
    });
  });
});
