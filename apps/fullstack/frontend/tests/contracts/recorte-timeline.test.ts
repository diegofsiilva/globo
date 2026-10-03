import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchCrosstab } from "@/app/(operations)/recorte/_lib/api-source";
import {
  toChronology,
  toCorrelationWindow,
  toMarker,
  toTimelineRows,
  windowAround,
} from "@/app/(operations)/timeline/_lib/adapt";
import type { TimelineApiResponse } from "@/app/(operations)/timeline/_lib/types";

describe("contratos das telas Recorte e Timeline", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("[TA-08] solicita as duas métricas do mapa de calor no mesmo crosstab", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        dimension_x: "entity",
        dimension_y: "hora_brt",
        cells: [
          { x: "LG webOS", y: "8", metric: "sessions", value: 120, points: 2 },
          { x: "LG webOS", y: "8", metric: "error_rate_pct", value: 8.5, points: 2 },
        ],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await fetchCrosstab({
      dimensionX: "entity",
      dimensionY: "hora_brt",
      metrics: ["sessions", "error_rate_pct"],
      scope: { source: "youbora_device" },
    });

    const endpoint = new URL(String(fetchMock.mock.calls[0][0]));
    expect(endpoint.searchParams.getAll("metric")).toEqual(["sessions", "error_rate_pct"]);
    expect(endpoint.searchParams.get("source")).toBe("youbora_device");
    expect(response.cells.map((cell) => cell.count)).toEqual([120, 8.5]);
  });

  test("[TA-09] mantém seis fontes ordenadas e uma cronologia atribuída", () => {
    const response: TimelineApiResponse = {
      window: {
        from: "2026-07-14T09:00:00.000Z",
        to: "2026-07-14T12:00:00.000Z",
      },
      limit_per_lane: 100,
      truncated: false,
      lanes: [
        {
          source: "servicenow",
          label: "ServiceNow",
          lane_type: "incidents",
          count: 1,
          truncated: false,
          points: [
            {
              window_id: 1,
              ts_start: "2026-07-14T11:00:00.000Z",
              ts_end: "2026-07-14T11:30:00.000Z",
              origem: "incidents",
              ref_id: "INC001",
              verdict: "external",
              severity: "1",
              provenance: "servicenow",
            },
          ],
        },
        ...["apollo", "tsuru", "npaw", "newrelic", "prometheus"].map((source) => ({
          source,
          label: source.toUpperCase(),
          lane_type: "series" as const,
          count: 1,
          truncated: false,
          points: [
            {
              bucket_ts: "2026-07-14T10:00:00.000Z",
              entity: `${source}-entity`,
              metric: "sessions",
              value: 10,
            },
          ],
        })),
      ],
    };

    const rows = toTimelineRows(response);
    const chronology = toChronology(response);
    const correlation = toCorrelationWindow(response);

    expect(rows.map((row) => row.label)).toEqual([
      "Player QoE",
      "CDN",
      "Backend",
      "Identidade",
      "Deploy",
      "Incidentes",
    ]);
    expect(chronology).toHaveLength(6);
    expect(chronology.at(-1)).toMatchObject({ source: "SERVICENOW" });
    expect(correlation.metrics[0].value).toBe("6 de 6");
    // A cronologia mistura dias (incidente aberto antes da janela), então cada
    // linha carrega o dia junto da hora.
    expect(chronology[0].hour).toMatch(/^\d{2}\/\d{2} \d{2}:\d{2}$/);
    // Sem hipótese na URL, o cartão não fala de hipótese.
    expect(correlation.metrics.map((metric) => metric.label)).not.toContain("Hipótese líder");
    expect(toCorrelationWindow(response, "42").metrics.at(-1)).toEqual({
      label: "Hipótese em análise",
      value: "#42",
    });
  });

  test("[TA-10] centra a janela na hipótese sem passar do presente virtual", () => {
    const simNow = new Date("2026-07-14T12:00:00.000Z");

    // Instante antigo: fica no meio da janela de 3 h.
    expect(windowAround(new Date("2026-07-14T06:00:00.000Z"), simNow, 180)).toEqual({
      from: "2026-07-14T04:30:00.000Z",
      to: "2026-07-14T07:30:00.000Z",
    });
    // Instante recente: a janela recua para terminar em sim.now(), porque as
    // views não devolvem nada além dele.
    expect(windowAround(new Date("2026-07-14T11:30:00.000Z"), simNow, 180)).toEqual({
      from: "2026-07-14T09:00:00.000Z",
      to: "2026-07-14T12:00:00.000Z",
    });
  });

  test("[TA-11] posiciona a hipótese no eixo só quando ela cai na janela", () => {
    const response = {
      window: { from: "2026-07-14T09:00:00.000Z", to: "2026-07-14T12:00:00.000Z" },
      limit_per_lane: 100,
      truncated: false,
      lanes: [],
    } satisfies TimelineApiResponse;

    expect(toMarker(response, "2026-07-14T10:30:00.000Z")).toBe(50);
    expect(toMarker(response, "2026-07-13T10:30:00.000Z")).toBeNull();
    expect(toMarker(response, "nao-e-data")).toBeNull();
  });
});
