/** Interface auxiliar, acessada por URL e ausente da navegação principal. */
import { Database, Files, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Apresenta a primeira etapa sem prometer envio ainda não implementado. */
export function IngestaoContent() {
  return (
    <section data-operations-slot="content" className="min-w-0 p-4 md:p-8">
      <div className="mx-auto grid max-w-6xl gap-6">
        <header className="grid gap-3 border-b border-border pb-6">
          <p className="flex items-center gap-2 font-mono text-micro uppercase tracking-widest text-primary">
            <Database className="size-4" aria-hidden="true" /> Ferramenta auxiliar
          </p>
          <h1 className="text-display font-semibold tracking-tight">Ingestão por arquivos</h1>
          <p className="max-w-2xl text-body text-muted-foreground">
            Prepare um lote de telemetria a partir de arquivos CSV ou Parquet.
            Nesta etapa, os arquivos ficam apenas no seu navegador.
          </p>
        </header>
        <ol aria-label="Etapas da ingestão" className="grid gap-3 sm:grid-cols-3">
          {[
            ["01", "Selecionar arquivos", "Disponível nesta entrega"],
            ["02", "Revisar e mapear", "Próxima etapa"],
            ["03", "Enviar e acompanhar", "Próxima etapa"],
          ].map(([number, title, detail], index) => (
            <li key={number} aria-current={index === 0 ? "step" : undefined}
              className="flex gap-3 rounded-panel border border-border bg-surface p-4">
              <span className={index === 0 ? "font-mono text-section text-primary" : "font-mono text-section text-muted-foreground"}>{number}</span>
              <div><p className="text-body font-semibold">{title}</p><p className="mt-1 text-label text-muted-foreground">{detail}</p></div>
            </li>
          ))}
        </ol>
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
          <section className="grid gap-4 rounded-panel border border-border bg-surface p-5" aria-labelledby="arquivos-titulo">
            <h2 id="arquivos-titulo" className="flex items-center gap-2 text-section font-semibold"><Files className="size-4 text-primary" aria-hidden="true" /> Arquivos do lote</h2>
            <p className="text-body text-muted-foreground">A seleção local será preparada nesta primeira entrega.</p>
          </section>
          <aside className="grid gap-4 rounded-panel border border-border bg-surface p-5" aria-labelledby="preparo-titulo">
            <h2 id="preparo-titulo" className="text-section font-semibold">Antes de começar</h2>
            <p className="text-body text-muted-foreground">Separe arquivos CSV ou Parquet. Você poderá revisar o lote antes de enviar.</p>
            <div className="border-t border-border pt-4 text-label text-muted-foreground">
              A leitura dos dados, o mapeamento de colunas e o envio serão habilitados na próxima etapa.
            </div>
            <Button disabled aria-describedby="envio-pendente">Continuar para revisão <ArrowRight aria-hidden="true" /></Button>
            <p id="envio-pendente" className="text-micro text-muted-foreground">Revisão e ingestão ainda indisponíveis.</p>
          </aside>
        </div>
      </div>
    </section>
  );
}
