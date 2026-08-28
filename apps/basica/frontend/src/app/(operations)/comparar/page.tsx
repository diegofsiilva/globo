import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import { CompararContent } from "./_components/comparar-content";

/** Título e descrição da aba do navegador para a tela Comparar. */
export const metadata: Metadata = {
  title: "Comparar · Monitoração Agêntica",
  description: "Janela atual contra referências históricas de volume de eventos",
};

/** Compõe a rota de comparação histórica; o estado operacional vive em CompararContent. */
export default function CompararPage() {
  return (
    <QueryProvider>
      <CompararContent />
    </QueryProvider>
  );
}
