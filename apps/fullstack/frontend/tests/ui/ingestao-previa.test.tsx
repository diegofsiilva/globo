/** Ciclo de vida da prévia assíncrona e descarte de resultados antigos. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SelecaoArquivos } from "@/app/(operations)/ingestao/_components/selecao-arquivos";
import { PreviaArquivo } from "@/app/(operations)/ingestao/_components/previa-arquivo";
import type { RespostaPrevia } from "@/app/(operations)/ingestao/_lib/previa-contrato";

class WorkerTeste {
  onmessage: ((evento: MessageEvent<RespostaPrevia>) => void) | null = null;
  onerror: (() => void) | null = null;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() { workers.push(this); }
}

let workers: WorkerTeste[];
const arquivo = new File(["id,valor\n001,teste"], "dados.csv", { lastModified: 1 });
const resposta: RespostaPrevia = {
  previa: { formato: "CSV", colunas: [{ nome: "id", tipo: "texto (amostra)" }],
    linhas: [["<script>teste</script>"]], totalLinhas: null, avisos: [] },
};

beforeEach(() => {
  workers = [];
  vi.stubGlobal("Worker", WorkerTeste);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("prévia assíncrona", () => {
  it("abre pelo lote e renderiza os valores como texto, encerrando o worker", () => {
    const { container } = render(<SelecaoArquivos />);
    fireEvent.change(screen.getByLabelText("Arquivos CSV ou Parquet"), { target: { files: [arquivo] } });
    fireEvent.click(screen.getByRole("button", { name: "Ver prévia de dados.csv" }));
    expect(screen.getByText("Lendo a amostra no navegador…")).toBeVisible();
    expect(workers[0].postMessage).toHaveBeenCalledWith(arquivo);
    act(() => workers[0].onmessage?.({ data: resposta } as MessageEvent<RespostaPrevia>));
    expect(screen.getByRole("table", { name: "Amostra de dados.csv" })).toBeVisible();
    expect(screen.getByText("<script>teste</script>")).toBeVisible();
    expect(container.querySelector("script")).toBeNull();
    expect(workers[0].terminate).toHaveBeenCalledOnce();
  });

  it("cancela uma leitura ao remover o arquivo e ignora sua resposta tardia", () => {
    render(<SelecaoArquivos />);
    fireEvent.change(screen.getByLabelText("Arquivos CSV ou Parquet"), { target: { files: [arquivo] } });
    fireEvent.click(screen.getByRole("button", { name: "Ver prévia de dados.csv" }));
    fireEvent.click(screen.getByRole("button", { name: "Remover dados.csv" }));
    expect(workers[0].terminate).toHaveBeenCalledOnce();
    act(() => workers[0].onmessage?.({ data: resposta } as MessageEvent<RespostaPrevia>));
    expect(screen.queryByRole("heading", { name: "Prévia do arquivo" })).not.toBeInTheDocument();
  });

  it("troca o arquivo da prévia e não mistura o resultado anterior", () => {
    const segundo = new File(["id\n2"], "novo.csv", { lastModified: 2 });
    render(<SelecaoArquivos />);
    fireEvent.change(screen.getByLabelText("Arquivos CSV ou Parquet"), { target: { files: [arquivo, segundo] } });
    fireEvent.click(screen.getByRole("button", { name: "Ver prévia de dados.csv" }));
    fireEvent.click(screen.getByRole("button", { name: "Ver prévia de novo.csv" }));
    expect(workers[0].terminate).toHaveBeenCalledOnce();
    act(() => workers[0].onmessage?.({ data: resposta } as MessageEvent<RespostaPrevia>));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    act(() => workers[1].onmessage?.({ data: { erro: "Arquivo incompleto." } } as MessageEvent<RespostaPrevia>));
    expect(screen.getByRole("alert")).toHaveTextContent("Arquivo incompleto.");
    fireEvent.click(screen.getByRole("button", { name: "Fechar prévia" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("interrompe a leitura por tempo e permite cancelar manualmente", () => {
    vi.useFakeTimers();
    const fechar = vi.fn();
    render(<PreviaArquivo arquivo={arquivo} onFechar={fechar} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar leitura" }));
    expect(fechar).toHaveBeenCalledOnce();
    act(() => vi.advanceTimersByTime(30_000));
    expect(workers[0].terminate).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert")).toHaveTextContent("excedeu 30 segundos");
  });

  it("limpar o lote também descarta a amostra em andamento", () => {
    render(<SelecaoArquivos />);
    fireEvent.change(screen.getByLabelText("Arquivos CSV ou Parquet"), { target: { files: [arquivo] } });
    fireEvent.click(screen.getByRole("button", { name: "Ver prévia de dados.csv" }));
    fireEvent.click(screen.getByRole("button", { name: "Limpar lote" }));
    expect(workers[0].terminate).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Cancelar leitura" })).not.toBeInTheDocument();
  });
});
