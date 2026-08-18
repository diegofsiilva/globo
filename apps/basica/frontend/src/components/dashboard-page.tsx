import { EventMonitor } from "@/components/event-monitor";
import { HypothesesScreen } from "@/components/hypotheses-screen";

type DashboardPageProps = {
  /** Área selecionada na navegação. As ainda não construídas caem no monitor. */
  section?: string;
};

/** Estrutura visual compartilhada pelas áreas navegáveis do dashboard. */
export function DashboardPage({ section }: DashboardPageProps) {
  return (
    <main className="app-shell">
      <header className="site-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true" />
          <strong>Monitoração Agêntica</strong>
          <span>Globoplay</span>
        </div>
      </header>
      {section === "hipoteses" ? <HypothesesScreen /> : <EventMonitor />}
    </main>
  );
}
