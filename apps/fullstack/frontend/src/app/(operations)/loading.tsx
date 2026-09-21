import { RefreshCw } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Esqueleto exibido enquanto o segmento da rota carrega.
 *
 * Esqueleto e não spinner: ele reserva o espaço que o conteúdo vai ocupar, e a
 * tela não salta quando o dado chega. `role="status"` faz o leitor de tela
 * anunciar o carregamento sem roubar o foco.
 */
export default function OperationsLoading() {
  return (
    <div className="col-start-1 row-start-2 grid min-w-0 gap-5 px-4 py-8 md:col-start-2 md:px-6" role="status">
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <RefreshCw className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        Carregando a próxima etapa da investigação…
      </div>
      <div className="grid gap-px overflow-hidden rounded-panel border border-border bg-border md:grid-cols-2">
        {[0, 1, 2, 3].map((item) => (
          <div className="space-y-4 bg-background p-5" key={item}>
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-8 w-3/4" />
            <Skeleton className="h-3 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
