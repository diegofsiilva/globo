/** Autorização, envio confirmado, acompanhamento e retomada na interface. */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AcessoIngestao } from "@/app/(operations)/ingestao/_components/acesso-ingestao";
import { MapeamentoArquivo } from "@/app/(operations)/ingestao/_components/mapeamento-arquivo";
import { ResultadosIngestao } from "@/app/(operations)/ingestao/_components/resultados-ingestao";
import { salvarJob, type FileJob } from "@/app/(operations)/ingestao/_lib/upload";
import { gravarTokenIngestao, lerTokenIngestao } from "@/lib/api/ingest-session";
import type { Previa } from "@/app/(operations)/ingestao/_lib/previa-contrato";

const job: FileJob = { id: "00000000-0000-4000-8000-000000000002", filename: "events.csv", status: "na_fila", total: 0, inserted: 0, duplicates: 0, rejected: 0, errors: [] };
const previa: Previa = { formato: "CSV", colunas: ["timestamp", "event_name", "session_id", "device_id"].map((nome) => ({ nome, tipo: "texto" })), linhas: [["2026-07-24T12:00:00Z", "session", "001", "tv"]], totalLinhas: null, avisos: [] };
beforeEach(() => { sessionStorage.removeItem("argus-ingest-token"); sessionStorage.removeItem("argus-file-jobs"); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); sessionStorage.removeItem("argus-ingest-token"); sessionStorage.removeItem("argus-file-jobs"); });

it("verifica o token antes de armazenar e libera o envio só após validar amostra", async () => {
  const fetch = vi.fn().mockImplementation((url: string) => Promise.resolve(Response.json(url.includes("session") ? { ok: true } : { job }, { status: url.includes("session") ? 200 : 202 }))); vi.stubGlobal("fetch", fetch);
  render(<><AcessoIngestao /><MapeamentoArquivo previa={previa} arquivo={new File(["original"], "events.csv")} /><ResultadosIngestao /></>);
  expect(screen.getByRole("button", { name: "Enviar arquivo" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Token de ingestão"), { target: { value: "b".repeat(64) } });
  fireEvent.click(screen.getByRole("button", { name: "Autorizar envio" }));
  expect(lerTokenIngestao()).toBeNull();
  await screen.findByText("Escrita autorizada nesta aba.");
  expect(screen.getByRole("button", { name: "Enviar arquivo" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Validar amostra" }));
  fireEvent.click(screen.getByRole("button", { name: "Enviar arquivo" }));
  await screen.findByText("Resultados da ingestão");
  expect(screen.getByText("Na fila")).toBeVisible();
  expect(screen.getByText(`Protocolo: ${job.id}`, { exact: true })).toBeVisible();
});

it("consulta jobs pendentes e mostra contadores e rejeições", async () => {
  vi.useFakeTimers(); gravarTokenIngestao("b".repeat(64)); salvarJob(job);
  const fetch = vi.fn().mockResolvedValue(Response.json({ job: { ...job, status: "concluido_com_rejeicoes", total: 12, inserted: 11, rejected: 1, errors: [{ linha: 12, campo: "device_id", mensagem: "Campo obrigatório vazio." }] } })); vi.stubGlobal("fetch", fetch);
  render(<ResultadosIngestao />);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(screen.getByText("Concluído com rejeições")).toBeVisible();
  expect(screen.getByText(/11 inseridos/)).toBeVisible();
  expect(screen.getByText(/Linha 12/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Baixar relatório de rejeições" })).toBeEnabled();
  await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("retoma falha transitória com o mesmo protocolo", async () => {
  gravarTokenIngestao("b".repeat(64)); salvarJob({ ...job, status: "falhou" });
  const fetch = vi.fn().mockResolvedValue(Response.json({ job }, { status: 202 })); vi.stubGlobal("fetch", fetch);
  render(<ResultadosIngestao />);
  fireEvent.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await waitFor(() => expect(screen.getByText("Na fila")).toBeVisible());
  expect(fetch.mock.calls[0][0]).toContain(`${job.id}/retry`);
});
