import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Recorte · Monitoração Agêntica",
  description: "Definição explícita e ajuste da população afetada",
};

export default function RecorteLayout({ children }: { children: ReactNode }) {
  return children;
}
