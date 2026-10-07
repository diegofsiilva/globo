import type { Metadata } from "next";
import { Suspense } from "react";
import { QueryProvider } from "@/providers/query-provider";
import { RecorteContent } from "./_components/recorte-content";

/** Título e descrição da aba do navegador para a tela Recorte. */
export const metadata: Metadata = {
  title: "Recorte · Monitoração Agêntica",
  description: "Definição explícita e ajuste da população afetada",
};

/** Compõe a rota de recorte afetado com dados reais da API de leitura. */
export default function RecortePage() {
  return (
    <QueryProvider>
      {/* O recorte é lido da query string, e no export estático isso exige um
          limite de Suspense. */}
      <Suspense fallback={null}>
        <RecorteContent />
      </Suspense>
    </QueryProvider>
  );
}
