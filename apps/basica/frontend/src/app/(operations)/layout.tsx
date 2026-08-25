import type { ReactNode } from "react";
import { OperationsNavigation } from "./_components/operations-navigation";
import styles from "./operations-layout.module.css";

/** Estrutura visual compartilhada por todas as páginas da aplicação. */
export default function OperationsLayout({ children }: { children: ReactNode }) {
  return (
    <div className={styles.appShell}>
      <a className={styles.skipLink} href="#main-content">
        Pular para o conteúdo
      </a>
      <header className={styles.siteHeader}>
        <div className={styles.brand}>
          <div className={styles.brandMark} aria-hidden="true" />
          <strong>Monitoração Agêntica</strong>
          <span>Globoplay</span>
        </div>
      </header>
      <main className={styles.routeGrid} id="main-content">
        <div className={styles.navigationSlot}>
          <OperationsNavigation />
        </div>
        {children}
      </main>
    </div>
  );
}
