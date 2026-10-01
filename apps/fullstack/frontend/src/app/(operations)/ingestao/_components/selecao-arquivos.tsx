"use client";

/** Seleção efêmera: referências a arquivos nunca saem do navegador. */
import { useRef, useState } from "react";
import { FileUp, File, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Permite selecionar, arrastar e retirar arquivos sem iniciar ingestão. */
export function SelecaoArquivos() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);

  /** Acrescenta arquivos escolhidos no seletor ou soltos na área. */
  function adicionar(novos: File[]) {
    setFiles((atuais) => [...atuais, ...novos]);
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
        <p id="arquivos-ajuda" className="text-label text-muted-foreground">CSV e Parquet · seleção múltipla</p>
        <Button type="button" variant="outline" onClick={() => inputRef.current?.click()}>Selecionar arquivos</Button>
        <input ref={inputRef} type="file" multiple accept=".csv,.parquet" className="sr-only"
          aria-label="Arquivos CSV ou Parquet" aria-describedby="arquivos-ajuda"
          onChange={(event) => {
            adicionar(Array.from(event.currentTarget.files ?? []));
            event.currentTarget.value = "";
          }} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="status" className="font-mono text-label text-muted-foreground">{files.length} arquivo(s) selecionado(s)</p>
        <Button type="button" variant="ghost" disabled={!files.length} onClick={() => setFiles([])}>Limpar lote</Button>
      </div>
      {files.length ? (
        <ul aria-label="Arquivos selecionados" className="divide-y divide-border rounded-panel border border-border">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className="flex min-w-0 items-center gap-3 p-3">
              <File className="size-5 shrink-0 text-primary" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="break-all text-body font-medium">{file.name}</p>
                <p className="font-mono text-micro text-muted-foreground">{file.name.split(".").pop()?.toUpperCase()} · {(file.size / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} MiB</p>
              </div>
              <Button type="button" variant="ghost" size="icon" aria-label={`Remover ${file.name}`}
                onClick={() => setFiles((atuais) => atuais.filter((_, position) => position !== index))}>
                <Trash2 aria-hidden="true" />
              </Button>
            </li>
          ))}
        </ul>
      ) : <p className="py-4 text-center text-body text-muted-foreground">Nenhum arquivo selecionado. Escolha um arquivo para preparar o lote.</p>}
      <p className="text-label text-muted-foreground">O lote será descartado ao sair ou recarregar esta página.</p>
    </div>
  );
}
