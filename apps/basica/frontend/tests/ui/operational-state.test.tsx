import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { OperationalStateBoundary } from "@/app/(operations)/_components/operational-state";

vi.mock("@/app/(operations)/_components/operations-ui-context", () => ({
  useOperationsUi: () => ({ demoState: null, clearDemoState: vi.fn() }),
}));

describe("estados operacionais compartilhados", () => {
  test("[TA-11] distingue carregamento, vazio e erro e permite nova tentativa", async () => {
    const onRetry = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    const { rerender } = render(
      <OperationalStateBoundary presentation={{ state: "loading", title: "Sinais" }}>
        <p>dados prontos</p>
      </OperationalStateBoundary>,
    );

    expect(screen.getByRole("status", { name: "Carregando Sinais" })).toBeVisible();
    expect(screen.queryByText("dados prontos")).not.toBeInTheDocument();

    rerender(
      <OperationalStateBoundary presentation={{ state: "empty", title: "Sinais" }}>
        <p>dados prontos</p>
      </OperationalStateBoundary>,
    );
    expect(screen.getByText("Nenhum resultado para sinais")).toBeVisible();

    rerender(
      <OperationalStateBoundary
        presentation={{
          state: "error",
          title: "Sinais",
          onRetry,
          failure: {
            kind: "timeout",
            cause: "A consulta excedeu o limite.",
            reference: "ARG-TEST-504",
            occurredAt: "09:00:00",
            retryable: true,
          },
        }}
      >
        <p>dados prontos</p>
      </OperationalStateBoundary>,
    );

    expect(screen.getByText("Não foi possível atualizar sinais")).toBeVisible();
    expect(screen.getByText("ARG-TEST-504")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
