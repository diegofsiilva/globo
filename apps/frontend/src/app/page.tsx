import { EventMonitor } from "@/components/event-monitor";

export default function Home() {
  return (
    <main>
      <header className="site-header">
        <span>Globoplay</span>
      </header>

      <div className="page">
        <section className="intro">
          <p className="eyebrow">Monitoramento de telemetria</p>
          <p>
            Consulte os eventos processados e entenda o possível problema
            percebido durante o uso do Globoplay.
          </p>
        </section>
        <EventMonitor />
      </div>
    </main>
  );
}
