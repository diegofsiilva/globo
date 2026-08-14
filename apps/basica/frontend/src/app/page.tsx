/** Página inicial do dashboard de telemetria. */
import { EventMonitor } from "@/components/event-monitor";

/** @returns Página principal com cabeçalho e monitor de eventos. */
export default function Home() {
  return (
    <main className="app-shell">
      <header className="site-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true" />
          <strong>Monitoração Agêntica</strong><span>Globoplay</span>
        </div>
      </header>
      <EventMonitor />
    </main>
  );
}
