import { EventMonitor } from "@/components/event-monitor";

export default function Home() {
  return (
    <main className="app-shell">
      <header className="site-header">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true" />
          <strong>Monitoração Agêntica</strong><span>Globoplay</span>
        </div>
        <div className="live-indicator"><i aria-hidden="true" />Dados simulados · 20:06:10</div>
      </header>
          <EventMonitor />
    </main>
  );
}
