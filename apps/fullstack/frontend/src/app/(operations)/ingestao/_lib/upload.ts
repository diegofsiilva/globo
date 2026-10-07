/** Contrato do serviço de arquivos e histórico operacional da aba atual. */
import { apiFetch } from "@/lib/api/client";
import { QuerySourceError } from "@/lib/operational-state";
import type { Mapeamento } from "./mapeamento";
import type { Previa } from "./previa-contrato";

/** Resultado durável de um arquivo, sem valores de telemetria ou credenciais. */
export type FileJob = {
  id: string; filename: string;
  status: "na_fila" | "processando" | "concluido" | "concluido_com_rejeicoes" | "rejeitado" | "falhou";
  total: number; inserted: number; duplicates: number; rejected: number;
  errors: { linha?: number; campo: string; mensagem: string }[];
};
const CHAVE = "argus-file-jobs";
const EVENTO = "argus-file-jobs-updated";
const ESTADOS = ["na_fila", "processando", "concluido", "concluido_com_rejeicoes", "rejeitado", "falhou"];

/** Confere o contrato externo antes de renderizar ou guardar metadados. */
function jobValido(value: unknown): value is FileJob {
  if (!value || typeof value !== "object") return false;
  const job = value as FileJob;
  return typeof job.id === "string" && /^[a-f0-9-]{36}$/i.test(job.id)
    && typeof job.filename === "string" && ESTADOS.includes(job.status)
    && [job.total, job.inserted, job.duplicates, job.rejected].every((n) => Number.isSafeInteger(n) && n >= 0)
    && Array.isArray(job.errors) && job.errors.length <= 100
    && job.errors.every((error) => error && typeof error.campo === "string" && typeof error.mensagem === "string" && (error.linha === undefined || Number.isSafeInteger(error.linha)));
}

/** Recusa respostas incompatíveis em vez de apresentar sucesso incorreto. */
function resultado(value: unknown): FileJob {
  const job = value && typeof value === "object" && "job" in value ? value.job : null;
  if (!jobValido(job)) throw new QuerySourceError("Resposta de ingestão inválida.", "invalid-response", "ARG-INGEST-CONTRACT", false);
  return job;
}

/** Lê um snapshot estável para useSyncExternalStore. */
export function snapshotJobs(): string {
  try { return sessionStorage.getItem(CHAVE) ?? "[]"; } catch { return "[]"; }
}

/** Descarta um histórico corrompido sem interromper uploads novos. */
export function lerJobs(snapshot: string): FileJob[] {
  try { const dados = JSON.parse(snapshot); return Array.isArray(dados) ? dados.filter(jobValido).slice(-50) : []; } catch { return []; }
}

/** Atualiza histórico sem armazenar dados de eventos ou tokens. */
export function salvarJob(job: FileJob): void {
  const jobs = lerJobs(snapshotJobs()).filter((item) => item.id !== job.id);
  // Falha de armazenamento não transforma um upload aceito em erro de envio.
  try { sessionStorage.setItem(CHAVE, JSON.stringify([...jobs, job].slice(-50))); } catch { return; }
  window.dispatchEvent(new Event(EVENTO));
}

/** Notifica upload, retry e polling na mesma aba. */
export function observarJobs(listener: () => void): () => void {
  window.addEventListener(EVENTO, listener);
  return () => window.removeEventListener(EVENTO, listener);
}

/** Envia o arquivo inteiro, nunca a amostra; servidor valida novamente. */
export async function enviarArquivo(arquivo: File, previa: Previa, mapping: Mapeamento): Promise<FileJob> {
  const nomes = Object.fromEntries(Object.entries(mapping).filter(([, index]) => index !== null && index !== undefined)
    .map(([field, index]) => [field, previa.colunas[index!].nome]));
  const data = new FormData();
  data.append("file", arquivo);
  data.append("mapping", JSON.stringify(nomes));
  if (previa.delimitador) data.append("delimiter", previa.delimitador);
  const resposta = await apiFetch<{ job: FileJob }>("/ingestion/v1/files", {
    ingestion: true, tag: "INGEST", method: "POST", formData: data, signal: AbortSignal.timeout(120_000),
  });
  const job = resultado(resposta);
  salvarJob(job);
  return job;
}

/** Consulta progresso e resultado usando a credencial de escrita. */
export async function consultarJob(id: string, signal?: AbortSignal): Promise<FileJob> {
  const resposta = await apiFetch<{ job: FileJob }>(`/ingestion/v1/jobs/${encodeURIComponent(id)}`, { ingestion: true, tag: "INGEST", signal });
  return resultado(resposta);
}

/** Retoma falha transitória sem duplicar eventos já gravados. */
export async function repetirJob(id: string): Promise<FileJob> {
  const resposta = await apiFetch<{ job: FileJob }>(`/ingestion/v1/jobs/${encodeURIComponent(id)}/retry`, { ingestion: true, tag: "INGEST", method: "POST" });
  const job = resultado(resposta);
  salvarJob(job);
  return job;
}
