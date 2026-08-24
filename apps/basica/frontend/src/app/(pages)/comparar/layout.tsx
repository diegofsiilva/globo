import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Comparar · Monitoração Agêntica",
  description: "Janela atual contra referências históricas, com significância estatística",
};

export default function CompararLayout({ children }: { children: ReactNode }) {
  return children;
}
