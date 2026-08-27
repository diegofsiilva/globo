import type { Metadata } from "next";
import { ExplorarScreen } from "./_components/explorar-screen";

export const metadata: Metadata = {
  title: "Explorar · Monitoração Agêntica",
  description: "Exploração de eventos de telemetria por atributos",
};

/** Compõe a rota demonstrativa de exploração temporal. */
export default function ExplorarPage() {
  return <ExplorarScreen />;
}
