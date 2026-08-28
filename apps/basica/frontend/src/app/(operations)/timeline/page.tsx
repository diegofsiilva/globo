import type { Metadata } from "next";
import { QueryProvider } from "@/providers/query-provider";
import { TimelineContent } from "./_components/timeline-content";

export const metadata: Metadata = {
  title: "Timeline · Monitoração Agêntica",
  description: "Seis fontes de telemetria e infraestrutura sobre um eixo temporal único",
};

/** Compõe a rota de timeline correlacionada. */
export default function TimelinePage() {
  return (
    <QueryProvider>
      <TimelineContent />
    </QueryProvider>
  );
}
