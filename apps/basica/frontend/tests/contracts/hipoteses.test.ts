import { afterEach, describe, expect, test, vi } from "vitest";

import { createHttpHypothesesSource } from "@/app/(operations)/hipoteses/_lib/http-source";
import { refineHypothesis } from "@/app/(operations)/hipoteses/_lib/refinement";

describe("contrato HTTP da tela Hipóteses", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("[TA-06] transforma a página publicada do backend em relatório explicável", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        count: 1,
        next_cursor: null,
        items: [
          {
            hypothesis_id: 17,
            family: "backend_internal",
            kind: "operational",
            title: "Falha interna de playback",
            summary: "Erro corroborado",
            scope: { service: "playback" },
            effect_start: "2026-07-14T11:30:00.000Z",
            effect_end: "2026-07-14T12:00:00.000Z",
            score: 82,
            coverage: 0.9,
            confidence: "high",
            evaluation_status: "generated",
            review_status: "pending",
            contradiction_strength: 0,
            sim_now: "2026-07-14T12:00:00.000Z",
            features: [
              {
                feature: "A",
                applicability: "available",
                value: 0.9,
                weight: 0.25,
                contribution: 0.225,
                explanation: "desvio confirmado",
              },
            ],
            evidence: [
              {
                evidence_id: 9,
                role: "subject",
                polarity: "favorable",
                explanation: "erro alto",
                source: "prometheus",
                entity: "playback",
                metric: "error_rate_pct",
                observed: 12,
                expected: 4,
                strength: 0.9,
                quality: 1,
                event_at: "2026-07-14T11:45:00.000Z",
              },
            ],
          },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const report = await createHttpHypothesesSource("http://api.test/")({
      from: "2026-07-14T11:30:00.000Z",
      to: "2026-07-14T12:00:00.000Z",
      scope: { source: "prometheus" },
    });

    const endpoint = new URL(String(fetchMock.mock.calls[0][0]));
    expect(endpoint.pathname).toBe("/api/v1/hypotheses");
    expect(endpoint.searchParams.get("source")).toBe("prometheus");
    expect(report.summary).toEqual({ hypotheses: 1, families: 1, sources: 1 });
    expect(report.hypotheses[0]).toMatchObject({
      id: "17",
      category: "falha interna de backend",
      score: 82,
      confidence: "alta",
      segment: "service=playback",
    });
    expect(report.hypotheses[0].factors[0].contribution).toBe(82);
    expect(report.hypotheses[0].evidence[0].detail).toContain("12 contra 4 esperado");
  });

  test("[TA-07] rejeita resposta sem lista de hipóteses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ count: 1 })));

    await expect(createHttpHypothesesSource("http://api.test")()).rejects.toMatchObject({
      kind: "invalid-response",
      reference: "ARG-HYP-INVALID-SHAPE",
      retryable: false,
    });
  });

  test("solicita refinamento da hipotese pelo cliente autenticado", async () => {
    const payload = {
      hypothesis_id: 17,
      answerable: true,
      answer: "A taxa de erro sustenta a hipotese.",
      claims: [
        { text: "A taxa de erro sustenta a hipotese.", source_ids: ["evidence.9"] },
      ],
      limitations: [],
      sources: [{ id: "evidence.9", value: { explanation: "erro alto" } }],
      model: "modelo-teste",
      grounding: "hypothesis_only",
    };
    const fetchMock = vi.fn().mockResolvedValue(Response.json(payload));
    vi.stubGlobal("fetch", fetchMock);

    await expect(refineHypothesis("17")).resolves.toEqual(payload);

    const [url, options] = fetchMock.mock.calls[0];
    expect(new URL(String(url)).pathname).toBe("/api/v1/hypotheses/17/refinement");
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe(`Bearer ${"a".repeat(64)}`);
    expect(JSON.parse(options.body)).toEqual({
      question: "Explique esta hipótese e as evidências que a sustentam.",
    });
  });
});
