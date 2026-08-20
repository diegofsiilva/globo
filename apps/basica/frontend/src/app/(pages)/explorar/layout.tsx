import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Explorar · Monitoração Agêntica",
  description: "Exploração de eventos de telemetria por atributos",
};

export default function ExplorarLayout({ children }: { children: ReactNode }) {
  return children;
}
