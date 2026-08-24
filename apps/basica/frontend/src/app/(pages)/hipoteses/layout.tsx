import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Hipóteses · Monitoração Agêntica",
  description: "Causas prováveis ranqueadas por score, com a decomposição de cada fator",
};

export default function HipotesesLayout({ children }: { children: ReactNode }) {
  return children;
}
