/** Contrato multipart, sessão do painel e histórico recuperável. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { enviarArquivo, lerJobs, salvarJob, snapshotJobs, type FileJob } from "@/app/(operations)/ingestao/_lib/upload";
import { apiFetch } from "@/lib/api/client";
import { gravarToken, lerToken } from "@/lib/api/session";
import type { Previa } from "@/app/(operations)/ingestao/_lib/previa-contrato";

const job: FileJob = { id: "00000000-0000-4000-8000-000000000001", filename: "events.csv", status: "na_fila", total: 0, inserted: 0, duplicates: 0, rejected: 0, errors: [] };
const previa: Previa = { formato: "CSV", colunas: ["data", "tipo", "sessao", "aparelho"].map((nome) => ({ nome, tipo: "texto" })), linhas: [["2026-07-24T12:00:00Z", "session", "001", "tv"]], totalLinhas: null, avisos: [], delimitador: ";" };

beforeEach(() => { sessionStorage.removeItem("argus-file-jobs"); gravarToken("b".repeat(64)); });
afterEach(() => { vi.unstubAllGlobals(); sessionStorage.removeItem("argus-file-jobs"); });

describe("envio de ingestão", () => {
  it("envia o arquivo inteiro com nomes mapeados e deixa o navegador definir boundary", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({ job }, { status: 202 })); vi.stubGlobal("fetch", fetch);
    const arquivo = new File(["conteúdo completo além da amostra"], "events.csv");
    await enviarArquivo(arquivo, previa, { timestamp: 0, event_name: 1, session_id: 2, device_id: 3 });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toContain("/ingestion/v1/files");
    expect(init.headers.Authorization).toBe(`Bearer ${"b".repeat(64)}`);
    expect(init.headers["Content-Type"]).toBeUndefined();
    expect(init.body.get("file")).toBe(arquivo);
    expect(JSON.parse(init.body.get("mapping"))).toEqual({ timestamp: "data", event_name: "tipo", session_id: "sessao", device_id: "aparelho" });
    expect(init.body.get("delimiter")).toBe(";");
    expect(lerJobs(snapshotJobs())).toEqual([job]);
  });

  it("401 do serviço de arquivos encerra a sessão do painel", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
    await expect(apiFetch("/ingestion/v1/session", { ingestion: true, tag: "INGEST" })).rejects.toMatchObject({ kind: "unauthorized" });
    expect(lerToken()).toBeNull();
  });

  it("não permite sucesso com um contrato de job inválido", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ job: { id: "incorreto", status: "sucesso" } })));
    await expect(enviarArquivo(new File(["x"], "events.csv"), previa, {})).rejects.toMatchObject({ kind: "invalid-response" });
    expect(lerJobs(snapshotJobs())).toEqual([]);
  });

  it("expõe a rejeição do servidor sem apagar a sessão", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ erro: "Fila cheia." }, { status: 422 })));
    await expect(apiFetch("/ingestion/v1/files", { ingestion: true, tag: "INGEST", method: "POST" })).rejects.toMatchObject({ message: "Fila cheia.", retryable: false });
    expect(lerToken()).toBeTruthy();
  });

  it("deduplica protocolos no histórico e ignora conteúdo corrompido", () => {
    salvarJob(job); salvarJob({ ...job, status: "concluido", total: 12, inserted: 12 });
    expect(lerJobs(snapshotJobs())).toHaveLength(1);
    expect(lerJobs(snapshotJobs())[0].inserted).toBe(12);
    expect(lerJobs('[null,{"id":"x","status":"na_fila"}]')).toEqual([]);
    expect(lerJobs("invalid-json")).toEqual([]);
  });
});
