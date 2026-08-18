import type { ReactNode } from "react";

/** Estrutura visual compartilhada por todas as páginas da aplicação. */
export default function PagesLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Pular para o conteúdo
      </a>
      <header className="site-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true" />
          <strong>Monitoração Agêntica</strong>
          <span>Globoplay</span>
        </div>
      </header>
      {children}
    </div>
  );
}
