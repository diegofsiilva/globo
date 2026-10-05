/** Página auxiliar de preparação da ingestão por arquivos. */
import type { Metadata } from "next";
import { IngestaoContent } from "./_components/ingestao-content";

/** Identifica a ferramenta auxiliar na aba do navegador. */
export const metadata: Metadata = {
  title: "Ingestão por arquivos · Monitoração Agêntica",
  description: "Preparação local de arquivos CSV e Parquet para ingestão",
};

/** Mantém a rota estática; a seleção de arquivos ocorre no navegador. */
export default function IngestaoPage() {
  return <IngestaoContent />;
}
