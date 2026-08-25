import type { Metadata } from "next";
import { ScreenFrame } from "../_components/screen-frame";
import { compareScope, scopeSummary } from "./_mocks/scenario";
import { CompararContent } from "./_components/comparar-content";

export const metadata: Metadata = {
  title: "Comparar · Monitoração Agêntica",
  description:
    "Janela atual contra referências históricas, com significância estatística",
};

/** Compõe a rota demonstrativa de comparação histórica. */
export default function CompararPage() {
  return (
    <ScreenFrame
      filters={compareScope.map((chip) => ({ ...chip, options: [chip.value] }))}
      scopeSummary={scopeSummary}
    >
      <CompararContent />
    </ScreenFrame>
  );
}
