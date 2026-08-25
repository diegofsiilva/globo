import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import { DashboardScreen } from "./_components/dashboard-screen";

export const metadata: Metadata = {
  title: "Monitoração Agêntica · Globoplay",
  description: "Análise de eventos de telemetria do Globoplay",
};

/** Compõe a rota integrada de consulta de eventos. */
export default function DashboardPage() {
  return (
    <QueryProvider>
      <DashboardScreen />
    </QueryProvider>
  );
}
