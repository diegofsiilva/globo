"use client";

/** Revisão manual da relação entre colunas locais e o envelope de eventos. */
import { useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CAMPOS_EVENTO, sugerirMapeamento, validarMapeamento, type Mapeamento, type ValidacaoMapeamento } from "../_lib/mapeamento";
import type { Previa } from "../_lib/previa-contrato";
import { lerTokenIngestao, observarTokenIngestao } from "@/lib/api/ingest-session";
import { enviarArquivo } from "../_lib/upload";

/** Inicializa sugestões exatas e invalida o resultado quando uma escolha muda.
 * @param previa Amostra vinculada ao arquivo aberto; nada é enviado à API.
 */
export function MapeamentoArquivo({ previa, arquivo }: { previa: Previa; arquivo?: File }) {
  const [mapeamento, setMapeamento] = useState<Mapeamento>(() => sugerirMapeamento(previa));
  const [resultado, setResultado] = useState<ValidacaoMapeamento | null>(null);
  const token = useSyncExternalStore(observarTokenIngestao, lerTokenIngestao, () => null);
  const [enviando, setEnviando] = useState(false);
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erroEnvio, setErroEnvio] = useState<string | null>(null);

  /** Substitui as escolhas e exige uma nova validação da amostra. */
  function atualizar(novo: Mapeamento) {
    setMapeamento(novo);
    setResultado(null);
  }

  return (
    <section className="grid min-w-0 gap-4 border-t border-border pt-4" aria-labelledby="mapeamento-titulo">
      <div>
        <h3 id="mapeamento-titulo" className="text-section font-semibold">Mapear colunas</h3>
        <p className="mt-2 text-body text-muted-foreground">Destino: eventos do app de TV. Campos com o mesmo nome são sugeridos automaticamente; confira cada escolha.</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" disabled={enviando} onClick={() => atualizar(sugerirMapeamento(previa))}>Sugerir pelo nome</Button>
        <Button type="button" variant="ghost" disabled={enviando} onClick={() => atualizar({})}>Limpar mapeamento</Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {CAMPOS_EVENTO.map((campo) => {
          const indice = mapeamento[campo.id];
          return (
            <div key={campo.id} className="grid min-w-0 content-start gap-2">
              <label htmlFor={`mapear-${campo.id}`} className="text-label font-semibold">
                <span className="font-mono">{campo.id}</span> <span className="font-normal text-muted-foreground">{campo.obrigatorio ? "· obrigatório" : "· opcional"}</span>
              </label>
              <Select value={indice === null || indice === undefined ? "nenhuma" : String(indice)}
                disabled={enviando}
                onValueChange={(valor) => atualizar({ ...mapeamento, [campo.id]: valor === "nenhuma" ? null : Number(valor) })}>
                <SelectTrigger id={`mapear-${campo.id}`} aria-describedby={`ajuda-${campo.id}`} className="w-full min-w-0 [&_span]:truncate"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="nenhuma">Não mapear</SelectItem>
                  {previa.colunas.map((coluna, index) => <SelectItem key={index} value={String(index)}>{coluna.nome}</SelectItem>)}
                </SelectContent>
              </Select>
              <p id={`ajuda-${campo.id}`} className="text-micro text-muted-foreground">{campo.ajuda}</p>
            </div>
          );
        })}
      </div>
      <Button type="button" className="justify-self-start" disabled={enviando} onClick={() => setResultado(validarMapeamento(previa, mapeamento))}>Validar amostra</Button>
      {resultado && (
        <div className="grid gap-3">
          <Alert variant={resultado.erros.length ? "destructive" : "default"}>
            <AlertTitle>{resultado.erros.length ? "Revise o mapeamento e os valores" : "Amostra sem erros nos campos mapeados"}</AlertTitle>
            <AlertDescription>
              <p>{resultado.linhasValidas} de {resultado.totalLinhas} linhas da amostra sem erros.</p>
              {resultado.erros.length > 0 && <ul className="mt-2 max-h-56 list-disc overflow-auto pl-4">
                {resultado.erros.map((erro, index) => <li key={index} className="break-words">{erro.linha ? `Linha ${erro.linha} · ` : ""}<span className="font-mono">{erro.campo}</span>: {erro.mensagem}</li>)}
              </ul>}
            </AlertDescription>
          </Alert>
          {resultado.avisos.map((aviso) => <p key={aviso} className="text-label text-warning">{aviso}</p>)}
        </div>
      )}
      <Button type="button" className="justify-self-start" disabled={!arquivo || !token || !resultado || resultado.erros.length > 0 || enviando}
        onClick={async () => {
          if (!arquivo) return;
          setEnviando(true); setMensagem(null); setErroEnvio(null);
          try { const job = await enviarArquivo(arquivo, previa, mapeamento); setMensagem(`Arquivo registrado. Protocolo: ${job.id}. Acompanhe o resultado abaixo.`); }
          catch (error) { setErroEnvio(error instanceof Error ? error.message : "Falha ao enviar arquivo."); }
          finally { setEnviando(false); }
        }}>{enviando ? "Enviando arquivo…" : "Enviar arquivo"}</Button>
      {!token && <p className="text-label text-warning">Autorize o acesso de ingestão para enviar.</p>}
      {mensagem && <p role="status" className="break-all text-body text-success">{mensagem}</p>}
      {erroEnvio && <p role="alert" className="text-body text-destructive">{erroEnvio} O arquivo pode já ter sido recebido; repetir o envio é seguro pela deduplicação.</p>}
      <p className="text-micro text-muted-foreground">Validação restrita às linhas da prévia. Ao enviar, o servidor valida o arquivo completo. As escolhas são descartadas ao fechar ou trocar a prévia; durante a prévia, nenhum dado é enviado.</p>
    </section>
  );
}
