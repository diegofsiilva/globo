import type { Metadata } from "next";
import { Suspense } from "react";
import { QueryProvider } from "@/providers/query-provider";
import { ExplorarScreen } from "./_components/explorar-screen";

/** Título e descrição da aba do navegador para a tela Explorar. */
export const metadata: Metadata = {
  title: "Explorar · Monitoração Agêntica",
  description: "Exploração de eventos de telemetria por atributos",
};

/** Compõe a rota demonstrativa de exploração temporal. */
export default function ExplorarPage() {
  return (
    <QueryProvider>
      {/* O recorte é lido da query string, e no export estático isso exige um
          limite de Suspense. */}
      <Suspense fallback={null}>
        <ExplorarScreen />
      </Suspense>
    </QueryProvider>
  );
}
