import { afterEach, describe, expect, test, vi } from "vitest";

import { resolveReference } from "@/app/(operations)/comparar/_lib/comparar-source";

describe("referências históricas da tela Comparar", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("[TA-04] preserva duração e horário ao comparar com ontem", async () => {
    const result = await resolveReference("ontem", {
      from: "2026-07-14T11:30:00.000Z",
      to: "2026-07-14T12:00:00.000Z",
    });

    expect(result).toMatchObject({
      from: "2026-07-13T11:30:00.000Z",
      to: "2026-07-13T12:00:00.000Z",
      found: true,
    });
  });

  test("[TA-05] consulta o backend para localizar a última janela estável", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        found: true,
        from: "2026-07-13T09:00:00.000Z",
        to: "2026-07-13T09:30:00.000Z",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await resolveReference("estavel", {
      from: "2026-07-14T11:30:00.000Z",
      to: "2026-07-14T12:00:00.000Z",
    });

    expect(new URL(String(fetchMock.mock.calls[0][0])).searchParams.get("duration_minutes")).toBe(
      "30",
    );
    expect(result).toMatchObject({
      from: "2026-07-13T09:00:00.000Z",
      to: "2026-07-13T09:30:00.000Z",
      found: true,
    });
  });
});
