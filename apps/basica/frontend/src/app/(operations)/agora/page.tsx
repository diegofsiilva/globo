import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import { AgoraScreen } from "./_components/agora-screen";

export const metadata: Metadata = {
  title: "Agora · Monitoração Agêntica",
  description: "Degradações e sinais operacionais em tempo real",
};

/** Compõe a rota demonstrativa Agora. */
export default function AgoraPage() {
  return (
    <QueryProvider>
      <AgoraScreen />
    </QueryProvider>
  );
}
