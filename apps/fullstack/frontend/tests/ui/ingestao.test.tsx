/** Validação da preparação local, sem acessar dados do parceiro. */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { IngestaoContent } from "@/app/(operations)/ingestao/_components/ingestao-content";
import { LIMITES, selecionarArquivos } from "@/app/(operations)/ingestao/_lib/selecao";
import { navigationItems } from "@/app/(operations)/_components/navigation-items";

afterEach(cleanup);

function arquivo(name: string, size = 12, lastModified = 1): File {
  const file = new File(["dado"], name, { lastModified });
  // Metadados sintéticos permitem testar limites sem alocar centenas de MiB.
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("limites do lote local", () => {
  it("aceita formatos em maiúsculas e MIME vazio", () => {
    const resultado = selecionarArquivos([], [arquivo("telemetria.CSV"), arquivo("eventos.PARQUET")]);
    expect(resultado.arquivos).toHaveLength(2);
    expect(resultado.avisos).toEqual([]);
  });

  it("preserva válidos quando a seleção contém formato inválido e arquivo vazio", () => {
    const resultado = selecionarArquivos([], [arquivo("errado.csv.exe"), arquivo("vazio.csv", 0), arquivo("ok.csv")]);
    expect(resultado.arquivos.map((file) => file.name)).toEqual(["ok.csv"]);
    expect(resultado.avisos).toEqual([
      "errado.csv.exe: formato não aceito. Use CSV ou Parquet.",
      "vazio.csv: arquivo vazio.",
    ]);
  });

  it("aceita exatamente 50 MiB e rejeita um byte além", () => {
    const resultado = selecionarArquivos([], [arquivo("limite.parquet", LIMITES.porArquivo), arquivo("grande.csv", LIMITES.porArquivo + 1)]);
    expect(resultado.arquivos).toHaveLength(1);
    expect(resultado.avisos[0]).toContain("excede 50 MiB");
  });

  it("deduplica dentro da seleção e entre seleções sem bloquear versões diferentes", () => {
    const file = arquivo("ok.csv");
    const primeiro = selecionarArquivos([], [file, file]);
    const segundo = selecionarArquivos(primeiro.arquivos, [file, arquivo("ok.csv", 12, 2)]);
    expect(primeiro.arquivos).toHaveLength(1);
    expect(segundo.arquivos).toHaveLength(2);
    expect(segundo.avisos[0]).toContain("já está no lote");
  });

  it("aceita dez arquivos e rejeita o décimo primeiro", () => {
    const resultado = selecionarArquivos([], Array.from({ length: 11 }, (_, index) => arquivo(`${index}.csv`)));
    expect(resultado.arquivos).toHaveLength(10);
    expect(resultado.avisos[0]).toContain("até 10 arquivos");
  });

  it("aceita exatamente 100 MiB no lote e rejeita excedente sem alterar os anteriores", () => {
    const atuais = [arquivo("a.parquet", LIMITES.porArquivo)];
    const resultado = selecionarArquivos(atuais, [arquivo("b.parquet", LIMITES.porArquivo), arquivo("extra.csv", 1)]);
    expect(resultado.arquivos).toHaveLength(2);
    expect(atuais).toHaveLength(1);
    expect(resultado.avisos[0]).toContain("excederia 100 MiB");
  });
});

describe("página auxiliar de ingestão", () => {
  it("não aparece na navegação e mantém a revisão indisponível", () => {
    expect(navigationItems.some((item) => item.href.startsWith("/ingestao"))).toBe(false);
    render(<IngestaoContent />);
    expect(screen.getByRole("heading", { level: 1, name: "Ingestão por arquivos" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Continuar para revisão" })).toBeDisabled();
    expect(screen.getByText(/conteúdo e o esquema ainda não são validados/)).toBeVisible();
  });

  it("seleciona, remove e permite escolher o mesmo arquivo novamente", async () => {
    const user = userEvent.setup();
    render(<IngestaoContent />);
    const input = screen.getByLabelText("Arquivos CSV ou Parquet");
    const file = arquivo("eventos.csv");
    await user.upload(input, file);
    expect(within(screen.getByRole("list", { name: "Arquivos selecionados" })).getByText("eventos.csv")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Remover eventos.csv" }));
    expect(screen.getByText(/Nenhum arquivo selecionado/)).toBeVisible();
    await user.upload(input, file);
    expect(screen.getByRole("button", { name: "Remover eventos.csv" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Limpar lote" }));
    expect(screen.queryByRole("list", { name: "Arquivos selecionados" })).not.toBeInTheDocument();
  });

  it("valida arquivos arrastados e informa rejeição de duplicata", async () => {
    const user = userEvent.setup();
    render(<IngestaoContent />);
    const area = screen.getByText("Arraste seus arquivos até aqui").parentElement!;
    const file = arquivo("amostra.parquet");
    fireEvent.drop(area, { dataTransfer: { files: [file, arquivo("errado.txt")] } });
    expect(screen.getByText("amostra.parquet")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("formato não aceito");
    fireEvent.drop(area, { dataTransfer: { files: [file] } });
    expect(screen.getByRole("alert")).toHaveTextContent("já está no lote");
    expect(screen.getByRole("status")).toHaveTextContent("1 arquivo(s)");
    await user.click(screen.getByRole("button", { name: "Limpar lote" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
