import type { ReactNode } from "react";
import { ThemeToggle } from "./_components/theme-toggle";
import {
  MobileOperationsNavigation,
  OperationsNavigation,
} from "./_components/operations-navigation";
import { operationsLayoutStyles as styles } from "./_components/operations-layout.styles";

/** Estrutura visual compartilhada por todas as páginas da aplicação. */
export default function OperationsLayout({ children }: { children: ReactNode }) {
  return (
    <div className={styles.appShell}>
      <a className={styles.skipLink} href="#main-content">
        Pular para o conteúdo
      </a>
      <header className={styles.siteHeader}>
        <MobileOperationsNavigation />
        <div className={styles.brand}>
          <div className={styles.brandMark} aria-hidden="true" />
          <strong>Monitoração Agêntica</strong>
          <span>Globoplay</span>
        </div>
        <div className={styles.headerActions}>
          <ThemeToggle />
        </div>
      </header>
      <main className={styles.routeGrid} id="main-content" tabIndex={-1}>
        <div className={styles.navigationSlot}>
          <OperationsNavigation />
        </div>
        {children}
      </main>
    </div>
  );
}
