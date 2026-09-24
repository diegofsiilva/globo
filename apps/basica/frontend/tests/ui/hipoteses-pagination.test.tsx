import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { test, expect, vi } from "vitest";

import { HipotesesScreen } from "@/app/(operations)/hipoteses/_components/hipoteses-screen";

const { fetchHypotheses } = vi.hoisted(() => ({ fetchHypotheses: vi.fn() }));

vi.mock("@/app/(operations)/hipoteses/_lib/hypotheses-source", () => ({ fetchHypotheses }));
vi.mock("@/app/(operations)/_components/operations-ui-context", () => ({
  useOperationsUi: () => ({ period: "3 h", hrefWithDemoState: (href: string) => href }),
}));
vi.mock("@/app/(operations)/_lib/sim-clock", () => ({
  useSimClock: () => ({
    snapshot: { simNow: "2026-07-12T12:00:00Z" },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  windowEndingAt: () => ({
    from: "2026-07-12T09:00:00Z",
    to: "2026-07-12T12:00:00Z",
  }),
}));
vi.mock("@/app/(operations)/_components/screen-frame", () => ({
  ScreenFrame: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

test("carrega automaticamente todas as páginas de hipóteses geradas", async () => {
  fetchHypotheses.mockImplementation(async ({ cursor }: { cursor?: string }) => ({
    nextCursor: cursor ? null : "pagina-2",
    window: { from: "", to: "", label: "09:00 – 12:00" },
    generated: 1,
    discarded: 0,
    scope: [],
    summary: { hypotheses: 1, families: 1, sources: 0 },
    hypotheses: [{
      id: cursor ? "2" : "1",
      category: "falha interna de backend",
      title: cursor ? "Segunda causa" : "Primeira causa",
      score: 80,
      confidence: "alta",
      factors: [],
      evidence: [],
      timelineAnchor: "2026-07-12T11:00:00Z",
      segment: "escopo global",
    }],
    discardedHypotheses: [],
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(<QueryClientProvider client={client}><HipotesesScreen /></QueryClientProvider>);
  expect(await screen.findByRole("button", { name: /Primeira causa/ })).toBeVisible();

  expect(await screen.findByRole("button", { name: /Segunda causa/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /Primeira causa/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /ID 1.*Primeira causa/ })).toBeVisible();
  expect(screen.getByRole("button", { name: /ID 2.*Segunda causa/ })).toBeVisible();
  expect(fetchHypotheses).toHaveBeenCalledTimes(2);
});
