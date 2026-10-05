/** Interações de revisão e invalidação do resultado ao mudar as escolhas. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MapeamentoArquivo } from "@/app/(operations)/ingestao/_components/mapeamento-arquivo";
import type { Previa } from "@/app/(operations)/ingestao/_lib/previa-contrato";

const previa: Previa = {
  formato: "CSV", colunas: ["timestamp", "event_name", "session_id", "device_id"].map((nome) => ({ nome, tipo: "texto" })),
  linhas: [["2026-10-05T12:00:00Z", "request", "001", "tv-1"]], totalLinhas: null, avisos: [],
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("formulário de mapeamento", () => {
  it("sugere os nomes iguais e aprova somente a amostra", () => {
    render(<MapeamentoArquivo previa={previa} />);
    expect(screen.getByRole("combobox", { name: /session_id/ })).toHaveTextContent("session_id");
    fireEvent.click(screen.getByRole("button", { name: "Validar amostra" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Amostra sem erros nos campos mapeados");
    expect(screen.getByRole("alert")).toHaveTextContent("1 de 1 linhas");
    expect(screen.getByText(/nenhum dado é enviado/)).toBeVisible();
  });

  it("limpar remove o resultado e expõe campos obrigatórios faltantes", () => {
    render(<MapeamentoArquivo previa={previa} />);
    fireEvent.click(screen.getByRole("button", { name: "Validar amostra" }));
    fireEvent.click(screen.getByRole("button", { name: "Limpar mapeamento" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Validar amostra" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Selecione uma coluna para este campo obrigatório.");
    fireEvent.click(screen.getByRole("button", { name: "Sugerir pelo nome" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Validar amostra" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Amostra sem erros");
  });

  it("a escolha manual invalida a aprovação e informa coluna reutilizada", async () => {
    // O jsdom não implementa APIs de scroll e captura utilizadas pelo Radix.
    Element.prototype.scrollIntoView ??= vi.fn();
    Element.prototype.hasPointerCapture ??= () => false;
    Element.prototype.setPointerCapture ??= vi.fn();
    Element.prototype.releasePointerCapture ??= vi.fn();
    const user = userEvent.setup();
    render(<MapeamentoArquivo previa={previa} />);
    await user.click(screen.getByRole("button", { name: "Validar amostra" }));
    const campo = screen.getByRole("combobox", { name: /device_id/ });
    campo.focus();
    await user.keyboard("[Enter]");
    await user.click(screen.getByRole("option", { name: "session_id", exact: true }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Validar amostra" }));
    expect(screen.getByRole("alert")).toHaveTextContent("já foi usada em session_id");
  });

  it("erro na amostra identifica linha e campo", () => {
    render(<MapeamentoArquivo previa={{ ...previa, linhas: [["2026-02-30T12:00:00Z", "request", "", "tv-1"]] }} />);
    fireEvent.click(screen.getByRole("button", { name: "Validar amostra" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Linha 1 · timestamp");
    expect(screen.getByRole("alert")).toHaveTextContent("Linha 1 · session_id");
    expect(screen.getByRole("alert")).toHaveTextContent("0 de 1 linhas");
  });
});
