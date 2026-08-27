import type { ReactNode } from "react";
import { OperationsShell } from "./_components/operations-shell";

/** Estrutura visual compartilhada por todas as páginas da aplicação. */
export default function OperationsLayout({ children }: { children: ReactNode }) {
  return <OperationsShell>{children}</OperationsShell>;
}
