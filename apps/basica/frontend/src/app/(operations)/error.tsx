"use client";

import { RefreshCw, TriangleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

const isProduction = process.env.NODE_ENV === "production";

export default function OperationsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="col-start-1 row-start-2 min-w-0 px-4 py-8 md:col-start-2 md:px-6">
      <Alert variant="destructive" className="max-w-3xl" aria-live="assertive">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Esta etapa não pôde ser exibida</AlertTitle>
        <AlertDescription className="space-y-4 text-foreground">
          <p>A renderização foi interrompida. O shell e os filtros globais continuam disponíveis.</p>
          <dl className="border-y border-destructive/30 py-3 font-mono text-xs">
            <dt className="text-muted-foreground">Referência técnica</dt>
            <dd className="mt-1 break-all">{error.digest ?? "ARG-UI-RENDER"}</dd>
            {/* Em produção a mensagem fica fora da tela de propósito: pode
                carregar caminho de arquivo e detalhe de infraestrutura. Em dev,
                escondê-la só obriga a caçar o erro no console. */}
            {!isProduction && error.message && (
              <>
                <dt className="mt-3 text-muted-foreground">Mensagem (apenas em desenvolvimento)</dt>
                <dd className="mt-1 whitespace-pre-wrap break-words">{error.message}</dd>
              </>
            )}
          </dl>
          <Button type="button" size="sm" onClick={reset}>
            <RefreshCw aria-hidden="true" />Tentar novamente
          </Button>
        </AlertDescription>
      </Alert>
    </div>
  );
}
