/** Layout raiz: configura metadados, tipografia e provedores globais. */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Archivo } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";

const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["400", "600"],
});

export const metadata: Metadata = {
  title: "Monitoração Agêntica · Globoplay",
  description: "Análise de eventos de telemetria do Globoplay",
};

/**
 * Monta o documento HTML compartilhado por todas as páginas.
 * @param children Conteúdo da rota renderizada pelo Next.js.
 * @returns Estrutura raiz da aplicação com seus provedores.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="pt-BR"
      className={`${archivo.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col"><Providers>{children}</Providers></body>
    </html>
  );
}
