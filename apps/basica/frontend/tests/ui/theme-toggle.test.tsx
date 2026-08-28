import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ThemeToggle } from "@/app/(operations)/_components/theme-toggle";
import { TooltipProvider } from "@/components/ui/tooltip";

const setTheme = vi.fn();

vi.mock("next-themes", () => ({
  useTheme: () => ({ resolvedTheme: "dark", setTheme }),
}));

describe("alternância acessível de tema", () => {
  beforeEach(() => setTheme.mockReset());

  test("[TA-10] anuncia e ativa o próximo tema pelo botão público", async () => {
    const user = userEvent.setup();
    render(
      <TooltipProvider>
        <ThemeToggle />
      </TooltipProvider>,
    );

    const toggle = await screen.findByRole("button", { name: "Usar modo claro" });
    await user.click(toggle);

    expect(setTheme).toHaveBeenCalledOnce();
    expect(setTheme).toHaveBeenCalledWith("light");
  });
});
