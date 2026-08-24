import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Timeline · Monitoração Agêntica",
  description: "Seis fontes de telemetria e infraestrutura sobre um eixo temporal único",
};

export default function TimelineLayout({ children }: { children: ReactNode }) {
  return children;
}
