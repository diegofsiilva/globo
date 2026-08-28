import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import { HipotesesScreen } from "./_components/hipoteses-screen";

/** Título e descrição da aba do navegador para a tela Hipóteses. */
export const metadata: Metadata = {
  title: "Hipóteses · Monitoração Agêntica",
  description:
    "Causas prováveis ranqueadas por score, com a decomposição de cada fator",
};

/** Compõe a rota de hipóteses com a fonte de dados escolhida no build. */
export default function HipotesesPage() {
  return (
    <QueryProvider>
      <HipotesesScreen />
    </QueryProvider>
  );
}
