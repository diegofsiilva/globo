"use client";

/** Autorização explícita de escrita, independente do acesso ao dashboard. */
import { useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api/client";
import { gravarTokenIngestao, lerTokenIngestao, limparTokenIngestao, observarTokenIngestao } from "@/lib/api/ingest-session";

/** Verifica a credencial antes de permitir upload; persiste só na sessão da aba. */
export function AcessoIngestao() {
  const token = useSyncExternalStore(observarTokenIngestao, lerTokenIngestao, () => null);
  const [valor, setValor] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  return (
    <section className="grid gap-3 rounded-panel border border-border bg-surface p-5" aria-labelledby="acesso-ingestao">
      <h2 id="acesso-ingestao" className="text-section font-semibold">Acesso de ingestão</h2>
      {token ? <div className="flex flex-wrap items-center gap-4"><p className="text-body text-success">Escrita autorizada nesta aba.</p><Button variant="ghost" onClick={limparTokenIngestao}>Encerrar acesso de ingestão</Button></div> : (
        <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]" onSubmit={async (event) => {
          event.preventDefault(); setErro(null);
          const candidato = valor.trim();
          if (!/^[a-f0-9]{64}$/i.test(candidato)) { setErro("Informe o token de ingestão com 64 caracteres hexadecimais."); return; }
          setOcupado(true);
          try { await apiFetch("/ingestion/v1/session", { ingestion: true, tag: "INGEST", token: candidato, signal: AbortSignal.timeout(15_000) }); gravarTokenIngestao(candidato); setValor(""); }
          catch (error) { setErro(error instanceof Error ? error.message : "Falha ao autorizar ingestão."); }
          finally { setOcupado(false); }
        }}>
          <div className="grid gap-2"><label htmlFor="token-ingestao" className="text-label">Token de ingestão</label><Input id="token-ingestao" type="password" value={valor} onChange={(event) => setValor(event.target.value)} autoComplete="off" disabled={ocupado} aria-describedby="token-ingestao-ajuda" /></div>
          <Button disabled={ocupado} className="self-end">{ocupado ? "Verificando…" : "Autorizar envio"}</Button>
        </form>
      )}
      <p id="token-ingestao-ajuda" className="text-label text-muted-foreground">Use a credencial de ingestão fornecida pela operação. O token de leitura não autoriza envio de arquivos.</p>
      {erro && <p role="alert" className="text-body text-destructive">{erro}</p>}
    </section>
  );
}
