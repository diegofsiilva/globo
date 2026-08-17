import { EventMonitor } from "@/components/event-monitor";

/** Estrutura visual compartilhada pelas áreas navegáveis do dashboard. */
export function DashboardPage() {
  return (
    <main className="app-shell">
      <header className="site-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true" />
          <strong>Monitoração Agêntica</strong>
          <span>Globoplay</span>
        </div>
      </header>
      <EventMonitor />
    </main>
  );
}
