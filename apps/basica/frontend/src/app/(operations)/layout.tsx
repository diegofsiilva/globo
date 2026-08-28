import type { ReactNode } from "react";
import { AccessGate } from "./_components/access-gate";
import { OperationsShell } from "./_components/operations-shell";

/**
 * Estrutura visual compartilhada por todas as páginas da aplicação.
 *
 * O portão de acesso fica FORA da moldura, e não dentro: sem token não há nada
 * a mostrar na navegação, no relógio nem no seletor de período — todos
 * dependem de consultas que voltariam 401. Uma moldura completa com seis telas
 * quebradas comunicaria "o sistema caiu", quando o que falta é o operador
 * informar o token.
 *
 * @param children Página da rota atual.
 */
export default function OperationsLayout({ children }: { children: ReactNode }) {
  return (
    <AccessGate>
      <OperationsShell>{children}</OperationsShell>
    </AccessGate>
  );
}
