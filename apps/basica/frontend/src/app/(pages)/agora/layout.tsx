import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Agora · Monitoração Agêntica",
  description: "Degradações e sinais operacionais em tempo real",
};

export default function AgoraLayout({ children }: { children: ReactNode }) {
  return children;
}
