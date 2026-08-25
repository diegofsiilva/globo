import type { Metadata } from "next";
import { ScreenFrame } from "../_components/screen-frame";
import { scopeSummary, timelineScope } from "./_mocks/scenario";
import { TimelineContent } from "./_components/timeline-content";

export const metadata: Metadata = {
  title: "Timeline · Monitoração Agêntica",
  description: "Seis fontes de telemetria e infraestrutura sobre um eixo temporal único",
};

/** Compõe a rota demonstrativa de timeline correlacionada. */
export default function TimelinePage() {
  return (
    <ScreenFrame
      filters={timelineScope.map((chip) => ({ ...chip, options: [chip.value] }))}
      scopeSummary={scopeSummary}
    >
      <TimelineContent />
    </ScreenFrame>
  );
}
