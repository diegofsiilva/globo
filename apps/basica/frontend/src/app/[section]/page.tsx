import { notFound } from "next/navigation";
import { DashboardPage } from "@/components/dashboard-page";

const SECTIONS = [
  "agora",
  "explorar",
  "comparar",
  "hipoteses",
  "timeline",
  "recorte",
] as const;

type Section = (typeof SECTIONS)[number];

/** Gera as seis URLs da navegação durante a exportação estática. */
export function generateStaticParams() {
  return SECTIONS.map((section) => ({ section }));
}

/** Impede a geração de rotas fora das seis seções conhecidas. */
function isSection(value: string): value is Section {
  return SECTIONS.some((section) => section === value);
}

/** Renderiza a área selecionada mantendo a estrutura compartilhada do dashboard. */
export default async function SectionPage({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;

  if (!isSection(section)) notFound();

  return <DashboardPage />;
}
