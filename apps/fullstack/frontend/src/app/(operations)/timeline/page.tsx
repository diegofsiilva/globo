import type { Metadata } from "next";
import { Suspense } from "react";
import { QueryProvider } from "@/providers/query-provider";
import { TimelineContent } from "./_components/timeline-content";

/** Título e descrição da aba do navegador para a tela Timeline. */
export const metadata: Metadata = {
  title: "Timeline · Monitoração Agêntica",
  description: "Seis fontes de telemetria e infraestrutura sobre um eixo temporal único",
};

/** Compõe a rota de timeline correlacionada. */
export default function TimelinePage() {
  return (
    <QueryProvider>
      {/* `TimelineContent` lê a query string (a hipótese que abriu a tela), e
          no export estático isso exige um limite de Suspense. */}
      <Suspense fallback={null}>
        <TimelineContent />
      </Suspense>
    </QueryProvider>
  );
}
