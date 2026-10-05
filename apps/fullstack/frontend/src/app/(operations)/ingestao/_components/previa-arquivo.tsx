"use client";

/** Prévia cancelável com parsing isolado em um worker local. */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LIMITES_PREVIA, type Previa, type RespostaPrevia } from "../_lib/previa-contrato";

type Estado = { fase: "lendo" } | { fase: "pronto"; previa: Previa } | { fase: "erro"; mensagem: string };

/** Mantém a amostra vinculada ao arquivo; desmontar encerra o worker e o timer.
 * @param arquivo Arquivo cuja amostra deve ser lida localmente.
 * @param onFechar Descarta a amostra e cancela uma leitura ainda em andamento.
 */
export function PreviaArquivo({ arquivo, onFechar }: { arquivo: File; onFechar: () => void }) {
  const [estado, setEstado] = useState<Estado>({ fase: "lendo" });

  useEffect(() => {
    let ativo = true;
    let worker: Worker | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    /** Encerra a tarefa antes de exibir o resultado ou a falha. */
    function finalizar(novo: Estado) {
      if (!ativo) return;
      ativo = false;
      worker?.terminate();
      clearTimeout(timer);
      setEstado(novo);
    }
    try {
      worker = new Worker(new URL("../_lib/previa.worker.ts", import.meta.url), { type: "module" });
      worker.onmessage = (evento: MessageEvent<RespostaPrevia>) => {
        finalizar("erro" in evento.data ? { fase: "erro", mensagem: evento.data.erro } : { fase: "pronto", previa: evento.data.previa });
      };
      worker.onerror = () => finalizar({ fase: "erro", mensagem: "Não foi possível abrir a prévia neste navegador. Feche e tente novamente." });
      timer = setTimeout(() => finalizar({ fase: "erro", mensagem: "A leitura excedeu 30 segundos e foi interrompida. Use um arquivo com registros ou grupos menores." }), LIMITES_PREVIA.tempoMs);
      worker.postMessage(arquivo);
    } catch {
      // Adia apenas esta falha síncrona para não atualizar estado no corpo do efeito.
      timer = setTimeout(() => finalizar({ fase: "erro", mensagem: "Este navegador não conseguiu iniciar a leitura local de arquivos." }), 0);
    }
    return () => { ativo = false; worker?.terminate(); clearTimeout(timer); };
  }, [arquivo]);

  return (
    <section aria-labelledby="previa-titulo" className="grid min-w-0 gap-4 rounded-panel border border-border bg-background p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 id="previa-titulo" className="text-section font-semibold">Prévia do arquivo</h3>
          <p className="mt-1 break-all text-label text-muted-foreground">{arquivo.name}</p>
        </div>
        <Button type="button" variant="ghost" onClick={onFechar}>{estado.fase === "lendo" ? "Cancelar leitura" : "Fechar prévia"}</Button>
      </div>
      {estado.fase === "lendo" && <p role="status" className="text-body text-muted-foreground">Lendo a amostra no navegador…</p>}
      {estado.fase === "erro" && <Alert variant="destructive"><AlertTitle>Prévia indisponível</AlertTitle><AlertDescription>{estado.mensagem}</AlertDescription></Alert>}
      {estado.fase === "pronto" && (
        <>
          <p role="status" className="font-mono text-label text-muted-foreground">
            {estado.previa.colunas.length} colunas · {estado.previa.linhas.length} linhas na amostra
            {estado.previa.totalLinhas !== null ? ` · ${estado.previa.totalLinhas} linhas no arquivo (metadados)` : " · total de linhas não calculado"}
            {estado.previa.delimitador && ` · separador: ${estado.previa.delimitador === "\t" ? "tabulação" : estado.previa.delimitador}`}
          </p>
          <Table aria-label={`Amostra de ${arquivo.name}`}>
            <TableHeader><TableRow>{estado.previa.colunas.map((coluna) => (
              <TableHead key={coluna.nome} className="min-w-36 max-w-64 align-top">
                <span className="block break-all text-label text-foreground">{coluna.nome}</span>
                <span className="mt-1 block text-micro font-normal text-muted-foreground">{coluna.tipo}</span>
              </TableHead>
            ))}</TableRow></TableHeader>
            <TableBody>{estado.previa.linhas.map((linha, index) => (
              <TableRow key={index}>{linha.map((valor, coluna) => <TableCell key={coluna} className="max-w-64 whitespace-pre-wrap break-all align-top text-label">{valor || <span className="text-muted-foreground">—</span>}</TableCell>)}</TableRow>
            ))}</TableBody>
          </Table>
          {!estado.previa.linhas.length && <p className="text-body text-muted-foreground">Nenhum registro disponível para exibir.</p>}
          {estado.previa.avisos.map((aviso) => <p key={aviso} className="text-label text-warning">{aviso}</p>)}
        </>
      )}
      <p className="text-micro text-muted-foreground">Amostra de até dez linhas. Valores exibidos são limitados a 500 caracteres por célula. A prévia não valida o arquivo inteiro nem os campos de destino. Nenhum dado foi enviado.</p>
    </section>
  );
}
