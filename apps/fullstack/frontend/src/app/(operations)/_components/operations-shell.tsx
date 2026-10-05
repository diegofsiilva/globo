"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { limparToken } from "@/lib/api/session";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { MobileOperationsNavigation, OperationsNavigation } from "./operations-navigation";
import { OperationsUiProvider, SCREEN_PERIODS, useOperationsUi } from "./operations-ui-context";
import { operationsLayoutStyles as styles } from "./operations-layout.styles";
import { ThemeToggle } from "./theme-toggle";
import { projectedSimNow, SimClockProvider, useSimClock } from "../_lib/sim-clock";

/**
 * Moldura das telas operacionais: cabeçalho, relógio virtual, período e navegação.
 *
 * Montada apenas com sessão ativa -- o portão de acesso fica acima dela, no
 * layout da rota.
 *
 * @param children Conteúdo da rota atual.
 */
export function OperationsShell({ children }: { children: ReactNode }) {
  return (
    <SimClockProvider>
      <OperationsUiProvider>
        <ShellContent>{children}</ShellContent>
      </OperationsUiProvider>
    </SimClockProvider>
  );
}

function ShellContent({ children }: { children: ReactNode }) {
  const { period, setPeriod } = useOperationsUi();
  const { snapshot } = useSimClock();
  const clock = useClock();
  const liveLabel = snapshot?.speed === 0 ? "Simulação pausada" : "Ao vivo simulado";

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
            {liveLabel}{" "}
            {/* A data vai junto com a hora: o relógio é o do dataset, que vive
                semanas atrás do relógio de parede. Só com a hora, o operador
                não tem como saber de que dia são os sinais na tela. */}
            <time
              className="hidden sm:inline"
              dateTime={clock.iso}
              title="Relógio virtual do dataset, e não o do navegador"
            >
              · {clock.label}
            </time>
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
          {/* Sair descarta o token da aba. Existe porque `sessionStorage`
              sobrevive à navegação dentro da mesma aba: sem o botão, a única
              forma de encerrar a sessão seria fechar a aba, e numa máquina
              compartilhada ninguém lembra de fazer isso. */}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => limparToken()}
            title="Encerrar a sessão nesta aba"
          >
            Sair
          </Button>
        </div>
      </header>
      <main className={styles.routeGrid} id="main-content" tabIndex={-1}>
        <div className={styles.navigationSlot}><OperationsNavigation /></div>
        {children}
      </main>
    </div>
  );
}

/** Rótulo do relógio antes da primeira leitura de `/api/v1/clock`. */
const CLOCK_PLACEHOLDER = { label: "--/-- --:--:--", iso: undefined as string | undefined };

/** Dia e mês, para o operador situar a hora virtual sem abrir outra tela. */
const clockDateFormatter = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" });

function useClock(): typeof CLOCK_PLACEHOLDER {
  const { snapshot } = useSimClock();
  const [clock, setClock] = useState(CLOCK_PLACEHOLDER);

  useEffect(() => {
    const update = () => {
      if (!snapshot) {
        setClock(CLOCK_PLACEHOLDER);
        return;
      }
      const now = projectedSimNow(snapshot);
      setClock({
        label: `${clockDateFormatter.format(now)} ${now.toLocaleTimeString("pt-BR")}`,
        iso: now.toISOString(),
      });
    };
    const firstTick = window.setTimeout(update, 0);
    const timer = window.setInterval(update, 1_000);
    return () => {
      window.clearTimeout(firstTick);
      window.clearInterval(timer);
    };
  }, [snapshot]);

  return clock;
}
