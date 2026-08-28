/** Layout raiz: configura metadados, tipografia e provedores globais. */
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/providers/theme-provider";
import "./globals.css";

const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

/** Metadados padrão do documento, herdados por toda rota que não os sobrescreva. */
export const metadata: Metadata = {
  title: "Monitoração Agêntica · Globoplay",
  description: "Análise de eventos de telemetria do Globoplay",
};

/**
 * Cor da barra do navegador, por esquema de cor do sistema.
 *
 * Precisa acompanhar o tema: sem isto, a barra fica clara sobre um dashboard
 * escuro no iOS, e a emenda entre as duas aparece como uma faixa branca no topo.
 */
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f2ef" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
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
      suppressHydrationWarning
      data-scroll-behavior="smooth"
      className={`${archivo.variable} ${ibmPlexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          storageKey="argus-theme"
          disableTransitionOnChange
        >
          <TooltipProvider>{children}</TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
