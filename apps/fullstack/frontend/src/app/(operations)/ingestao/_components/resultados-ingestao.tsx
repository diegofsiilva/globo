"use client";

/** Acompanhamento do resultado durável; não confunde upload com gravação. */
import { useEffect, useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { lerTokenIngestao, observarTokenIngestao } from "@/lib/api/ingest-session";
import { consultarJob, lerJobs, observarJobs, repetirJob, salvarJob, snapshotJobs, type FileJob } from "../_lib/upload";

const LABELS = { na_fila: "Na fila", processando: "Processando", concluido: "Concluído", concluido_com_rejeicoes: "Concluído com rejeições", rejeitado: "Arquivo rejeitado", falhou: "Falha temporária" };

/** Gera relatório de problemas sem incluir valores das linhas rejeitadas. */
function baixarRelatorio(job: FileJob) {
  const url = URL.createObjectURL(new Blob([JSON.stringify({ id: job.id, total: job.total, rejected: job.rejected, errors: job.errors }, null, 2)], { type: "application/json" }));
  const link = document.createElement("a"); link.href = url; link.download = `rejeicoes-${job.id}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Retoma consultas após recarregar a aba e permite repetir falhas transitórias. */
export function ResultadosIngestao() {
  const snapshot = useSyncExternalStore(observarJobs, snapshotJobs, () => "[]");
  const token = useSyncExternalStore(observarTokenIngestao, lerTokenIngestao, () => null);
  const jobs = lerJobs(snapshot);
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState<string | null>(null);
  useEffect(() => {
    const ativos = lerJobs(snapshot).filter((job) => job.status === "na_fila" || job.status === "processando");
    if (!token || !ativos.length) return;
    const controller = new AbortController();
    let consultando = false;
    const timer = setInterval(async () => {
      if (consultando) return;
      consultando = true;
      const respostas = await Promise.allSettled(ativos.map((job) => consultarJob(job.id, AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]))));
      if (!controller.signal.aborted) {
        let falha: string | null = null;
        for (const resposta of respostas) {
          if (resposta.status === "fulfilled") salvarJob(resposta.value);
          else falha = resposta.reason instanceof Error ? resposta.reason.message : "Falha ao consultar resultado.";
        }
        setErro(falha);
      }
      consultando = false;
    }, 2000);
    return () => { clearInterval(timer); controller.abort(); };
  }, [snapshot, token]);
  if (!jobs.length) return null;
  return (
    <section className="grid gap-4 rounded-panel border border-border bg-surface p-5" aria-labelledby="resultados-ingestao">
      <h2 id="resultados-ingestao" className="text-section font-semibold">Resultados da ingestão</h2>
      <p className="text-label text-muted-foreground">Resultados dos últimos 50 envios desta aba. O processamento continua no servidor ao fechar a página.</p>
      {erro && <p role="alert" className="text-body text-destructive">{erro}</p>}
      {jobs.map((job) => <article key={job.id} className="grid min-w-0 gap-2 rounded-control border border-border p-4">
        <h3 className="break-all text-body font-semibold">{job.filename}</h3>
        <p className="text-body" role="status">{LABELS[job.status]}</p>
        <p className="text-label text-muted-foreground">{job.total} registros · {job.inserted} inseridos · {job.duplicates} duplicados · {job.rejected} rejeitados</p>
        <p className="break-all font-mono text-micro text-muted-foreground">Protocolo: {job.id}</p>
        {job.errors.length > 0 && <><ul className="max-h-48 list-disc overflow-auto pl-4 text-label text-destructive">{job.errors.map((error, index) => <li key={index}>{error.linha ? `Linha ${error.linha} · ` : ""}{error.campo}: {error.mensagem}</li>)}</ul><p className="text-micro text-muted-foreground">Até 100 motivos exibidos; o contador inclui todas as rejeições.</p><Button className="justify-self-start" variant="outline" onClick={() => baixarRelatorio(job)}>Baixar relatório de rejeições</Button></>}
        {job.status === "falhou" && <Button className="justify-self-start" disabled={!token || ocupado === job.id} onClick={async () => { setOcupado(job.id); try { await repetirJob(job.id); setErro(null); } catch (error) { setErro(error instanceof Error ? error.message : "Falha ao repetir envio."); } finally { setOcupado(null); } }}>Tentar novamente</Button>}
      </article>)}
    </section>
  );
}
