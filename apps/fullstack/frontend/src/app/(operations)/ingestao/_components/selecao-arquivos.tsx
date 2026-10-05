"use client";

/** Seleção efêmera: referências a arquivos nunca saem do navegador. */
import { useReducer, useRef, useState } from "react";
import { FileUp, File, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { chaveArquivo, formatoArquivo, selecionarArquivos, type Selecao } from "../_lib/selecao";
import { PreviaArquivo } from "./previa-arquivo";

type Acao = { tipo: "adicionar"; arquivos: File[] } | { tipo: "remover"; chave: string } | { tipo: "limpar" };

/** Atualiza lote e avisos juntos, inclusive em seleções consecutivas. */
function atualizarSelecao(estado: Selecao, acao: Acao): Selecao {
  if (acao.tipo === "adicionar") return selecionarArquivos(estado.arquivos, acao.arquivos);
  if (acao.tipo === "limpar") return { arquivos: [], avisos: [] };
  return { arquivos: estado.arquivos.filter((arquivo) => chaveArquivo(arquivo) !== acao.chave), avisos: [] };
}

/** Permite selecionar, arrastar e retirar arquivos sem iniciar ingestão. */
export function SelecaoArquivos() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [selecao, dispatch] = useReducer(atualizarSelecao, { arquivos: [], avisos: [] });
  const files = selecao.arquivos;
  const [dragging, setDragging] = useState(false);
  const [chavePrevia, setChavePrevia] = useState<string | null>(null);
  const arquivoPrevia = files.find((file) => chaveArquivo(file) === chavePrevia);

  /** Acrescenta arquivos escolhidos no seletor ou soltos na área. */
  function adicionar(novos: File[]) {
    dispatch({ tipo: "adicionar", arquivos: novos });
  }

  return (
    <div className="grid gap-5">
      <div
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={(event) => {
          event.preventDefault(); setDragging(false);
          adicionar(Array.from(event.dataTransfer.files));
        }}
        className={cn("grid justify-items-center gap-3 rounded-panel border-2 border-dashed border-border bg-background p-6 text-center sm:p-10", dragging && "border-primary bg-primary/5")}
      >
        <FileUp className="size-8 text-primary" aria-hidden="true" />
        <p className="text-section font-semibold">Arraste seus arquivos até aqui</p>
        <p id="arquivos-ajuda" className="text-label text-muted-foreground">CSV e Parquet · até 50 MiB por arquivo<br />Até 10 arquivos e 100 MiB por lote</p>
        <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>Selecionar arquivos</Button>
        <input ref={inputRef} type="file" multiple accept=".csv,.parquet" className="sr-only"
          aria-label="Arquivos CSV ou Parquet" aria-describedby="arquivos-ajuda"
          onChange={(event) => {
            adicionar(Array.from(event.currentTarget.files ?? []));
            event.currentTarget.value = "";
          }} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="status" className="font-mono text-label text-muted-foreground">{files.length} arquivo(s) selecionado(s) · {(files.reduce((total, file) => total + file.size, 0) / 1024 ** 2).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} MiB</p>
        <Button type="button" variant="ghost" disabled={!files.length && !selecao.avisos.length} onClick={() => { setChavePrevia(null); dispatch({ tipo: "limpar" }); }}>Limpar lote</Button>
      </div>
      {selecao.avisos.length > 0 && (
        <Alert variant="destructive">
          <AlertTitle>Alguns arquivos não foram adicionados</AlertTitle>
          <AlertDescription>
            <ul className="max-h-48 list-disc overflow-auto pl-4">
              {selecao.avisos.map((aviso, index) => <li className="break-all" key={`${index}-${aviso}`}>{aviso}</li>)}
            </ul>
          </AlertDescription>
        </Alert>
      )}
      {files.length ? (
        <ul aria-label="Arquivos selecionados" className="divide-y divide-border rounded-panel border border-border">
          {files.map((file) => (
            <li key={chaveArquivo(file)} className="flex min-w-0 flex-wrap items-center gap-3 p-3">
              <File className="size-5 shrink-0 text-primary" aria-hidden="true" />
              <div className="min-w-0 flex-1 basis-32">
                <p className="break-all text-body font-medium">{file.name}</p>
                <p className="font-mono text-micro text-muted-foreground">{formatoArquivo(file.name)} · {(file.size / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} MiB</p>
              </div>
              <Button type="button" variant="outline" aria-label={`Ver prévia de ${file.name}`}
                aria-pressed={chavePrevia === chaveArquivo(file)} onClick={() => setChavePrevia(chaveArquivo(file))}>Ver prévia</Button>
              <Button type="button" variant="ghost" size="icon" aria-label={`Remover ${file.name}`}
                onClick={() => { if (chavePrevia === chaveArquivo(file)) setChavePrevia(null); dispatch({ tipo: "remover", chave: chaveArquivo(file) }); }}>
                <Trash2 aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      ) : <p className="py-4 text-center text-body text-muted-foreground">Nenhum arquivo selecionado. Escolha um arquivo para preparar o lote.</p>}
      {arquivoPrevia && <PreviaArquivo key={chaveArquivo(arquivoPrevia)} arquivo={arquivoPrevia} onFechar={() => setChavePrevia(null)} />}
      <p className="text-label text-muted-foreground">Esta seleção verifica extensão, tamanho e duplicatas. Use “Ver prévia” para conferir uma amostra e as colunas. O lote será descartado ao sair ou recarregar esta página.</p>
    </div>
  );
}
