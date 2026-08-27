"use client";

import { useEffect, useState, type ReactNode } from "react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { MobileOperationsNavigation, OperationsNavigation } from "./operations-navigation";
import { OperationsUiProvider, SCREEN_PERIODS, useOperationsUi } from "./operations-ui-context";
import { operationsLayoutStyles as styles } from "./operations-layout.styles";
import { ThemeToggle } from "./theme-toggle";

export function OperationsShell({ children }: { children: ReactNode }) {
  return (
    <OperationsUiProvider>
      <ShellContent>{children}</ShellContent>
    </OperationsUiProvider>
  );
}

function ShellContent({ children }: { children: ReactNode }) {
  const { period, setPeriod } = useOperationsUi();
  const clock = useClock();

  return (
    <div className={styles.appShell}>
      <a className={styles.skipLink} href="#main-content">Pular para o conteúdo</a>
      <header className={styles.siteHeader}>
        <div className={styles.identityRow}>
          <MobileOperationsNavigation />
          <div className={styles.brand}>
            <div className={styles.brandMark} aria-hidden="true" />
            <strong>Monitoração Agêntica</strong>
            <span>Globoplay</span>
          </div>
        </div>
        <div className={styles.controlRow} aria-label="Atualização e período">
          <p className={styles.liveStatus} aria-live="off">
            <span data-live-dot aria-hidden="true" />
            Ao vivo <span className="hidden sm:inline">· {clock}</span>
          </p>
          <ToggleGroup
            type="single"
            value={period ?? ""}
            onValueChange={(value) => value && setPeriod(value as (typeof SCREEN_PERIODS)[number])}
            aria-label="Período analisado"
            className={styles.periods}
          >
            {SCREEN_PERIODS.map((value) => (
              <ToggleGroupItem key={value} value={value}>{value}</ToggleGroupItem>
            ))}
          </ToggleGroup>
          <ThemeToggle />
        </div>
      </header>
      <main className={styles.routeGrid} id="main-content" tabIndex={-1}>
        <div className={styles.navigationSlot}><OperationsNavigation /></div>
        {children}
      </main>
    </div>
  );
}

function useClock(): string {
  const [clock, setClock] = useState("--:--:--");

  useEffect(() => {
    const update = () => setClock(new Date().toLocaleTimeString("pt-BR"));
    const firstTick = window.setTimeout(update, 0);
    const timer = window.setInterval(update, 1_000);
    return () => {
      window.clearTimeout(firstTick);
      window.clearInterval(timer);
    };
  }, []);

  return clock;
}
