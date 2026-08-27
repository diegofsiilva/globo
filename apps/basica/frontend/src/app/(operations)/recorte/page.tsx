import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import { RecorteContent } from "./_components/recorte-content";

export const metadata: Metadata = {
  title: "Recorte · Monitoração Agêntica",
  description: "Definição explícita e ajuste da população afetada",
};

/** Compõe a rota de recorte afetado com dados reais da API de leitura. */
export default function RecortePage() {
  return (
    <QueryProvider>
      <RecorteContent />
    </QueryProvider>
  );
}
