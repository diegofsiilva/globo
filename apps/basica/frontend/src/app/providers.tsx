"use client";

/** Provedores client-side compartilhados pela aplicação. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/**
 * Disponibiliza um cliente estável do TanStack Query para a árvore React.
 * @param children Componentes que consumirão o cliente de consultas.
 * @returns Árvore envolvida pelo provedor de consultas.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
  }));

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
