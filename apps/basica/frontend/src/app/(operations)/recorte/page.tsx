import type { Metadata } from "next";
import { ScreenFrame } from "../_components/screen-frame";
import { cutScope, scopeSummary } from "./_mocks/scenario";
import { RecorteContent } from "./_components/recorte-content";

export const metadata: Metadata = {
  title: "Recorte · Monitoração Agêntica",
  description: "Definição explícita e ajuste da população afetada",
};

/** Compõe a rota demonstrativa de recorte afetado. */
export default function RecortePage() {
  return (
    <ScreenFrame
      filters={cutScope.map((chip) => ({ ...chip, options: [chip.value] }))}
      scopeSummary={scopeSummary}
      operational={{ title: "Recorte afetado", scope: scopeSummary }}
    >
      <RecorteContent />
    </ScreenFrame>
  );
}
