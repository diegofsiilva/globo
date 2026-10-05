import { afterEach, describe, expect, test, vi } from "vitest";

import { createHttpHypothesesSource } from "@/app/(operations)/hipoteses/_lib/http-source";
import { HYPOTHESIS_FILTERS } from "@/app/(operations)/hipoteses/_lib/mapper";
import { refineHypothesis } from "@/app/(operations)/hipoteses/_lib/refinement";

describe("contrato HTTP da tela Hipóteses", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("[TA-06] transforma a página gerada do backend em relatório explicável", async () => {
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

    const report = await createHttpHypothesesSource()({
      from: "2026-07-14T11:30:00.000Z",
      to: "2026-07-14T12:00:00.000Z",
      scope: { source: "prometheus" },
    });

    const endpoint = new URL(String(fetchMock.mock.calls[0][0]));
    expect(endpoint.pathname).toBe("/api/v1/hypotheses");
    expect(endpoint.searchParams.get("source")).toBe("prometheus");
    expect(report.summary).toEqual({ hypotheses: 1, families: 1, sources: 1 });
    expect(report.nextCursor).toBeNull();
    expect(report.hypotheses[0]).toMatchObject({
      id: "17",
      category: "falha interna de backend",
      score: 82,
      confidence: "alta",
      segment: "service=playback",
    });
    expect(report.hypotheses[0].factors[0].contribution).toBe(82);
    expect(report.hypotheses[0].evidence[0].detail).toContain("12 contra 4 esperado");
    // O que permite triar sem abrir cada hipótese: quando, de que tipo, com
    // quanta evidência -- e de que lado cada evidência está.
    expect(report.hypotheses[0]).toMatchObject({
      summary: "Erro corroborado",
      kind: "operacional",
      coverage: 0.9,
    });
    expect(report.hypotheses[0].effect).toMatch(/^\d{2}\/\d{2} \d{2}:\d{2} → \d{2}:\d{2}$/);
    expect(report.hypotheses[0].evidence[0].polarity).toBe("a favor");
  });

  test("[TA-12] os filtros da tela enviam os valores que a API valida", () => {
    const valores = Object.fromEntries(
      HYPOTHESIS_FILTERS.map((filtro) => [filtro.key, filtro.options]),
    );

    // A rota responde 422 a valor fora do conjunto fechado: o rótulo em
    // português é só da tela.
    expect(valores.family["falha interna de backend"]).toBe("backend_internal");
    expect(Object.keys(valores.family)).toHaveLength(11);
    expect(valores.kind).toEqual({
      operacional: "operational",
      contexto: "context",
      "qualidade de dado": "data_quality",
    });
    expect(valores.confidence).toEqual({ alta: "high", média: "medium", baixa: "low" });
  });

  test("permite buscar a próxima página sem perder o recorte", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({ count: 0, next_cursor: "cursor-seguinte", items: [] }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const report = await createHttpHypothesesSource()({
      from: "2026-07-14T11:30:00.000Z",
      to: "2026-07-14T12:00:00.000Z",
      cursor: "cursor-anterior",
    });

    const endpoint = new URL(String(fetchMock.mock.calls[0][0]));
    expect(endpoint.searchParams.get("from")).toBe("2026-07-14T11:30:00.000Z");
    expect(endpoint.searchParams.get("to")).toBe("2026-07-14T12:00:00.000Z");
    expect(endpoint.searchParams.get("cursor")).toBe("cursor-anterior");
    expect(report.nextCursor).toBe("cursor-seguinte");
  });

  test("[TA-07] rejeita resposta sem lista de hipóteses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ count: 1 })));

    await expect(createHttpHypothesesSource()()).rejects.toMatchObject({
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
