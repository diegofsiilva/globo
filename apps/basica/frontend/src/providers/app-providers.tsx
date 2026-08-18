"use client";

/** Provedores client-side compartilhados por toda a aplicação. */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/** Disponibiliza as dependências globais para a árvore React. */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 30_000,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
