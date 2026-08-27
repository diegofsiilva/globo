import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import { DashboardScreen } from "./_components/dashboard-screen";

export const metadata: Metadata = {
  title: "Monitor de eventos · Monitoração Agêntica",
  description: "Consulta de eventos de telemetria do Globoplay conectada à API de leitura",
};

/** Compõe a rota de consulta de eventos conectada ao cliente HTTP real. */
export default function MonitorPage() {
  return (
    <QueryProvider>
      <DashboardScreen />
    </QueryProvider>
  );
}
