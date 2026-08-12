"use client";

import { useState } from "react";

type SimulatedEvent = {
  id: string;
  time: string;
  eventName: string;
  manufacturer: string;
  model: string;
  modelYear: string;
  platform: string;
  version: string;
  route: string;
  duration?: string;
  status: "normal" | "attention";
  classification: string;
  technicalDetail: string;
  userEffect: string;
  displayedMessage: string;
  source: string;
  processingStatus: "Processado" | "Recebido" | "Erro no processamento";
};

// Dados simulados a partir dos seis CSVs fornecidos. Identificadores pessoais,
// de sessão e de dispositivo foram omitidos intencionalmente.
const events: SimulatedEvent[] = [
  {
    id: "evt-error-philco",
    time: "20:04:11",
    eventName: "error",
    manufacturer: "Philco",
    model: "BTV32D10N5SKH",
    modelYear: "2021",
    platform: "NetRange",
    version: "2026.3.0",
    route: "VOD",
    status: "attention",
    classification: "Erro ao reproduzir vídeo",
    technicalDetail: "dash_shaka_playback:6_6002",
    userEffect: "O usuário tentou assistir a um vídeo, mas a reprodução falhou.",
    displayedMessage: "Para assistir, tente carregar novamente",
    source: "Loader · dataset histórico",
    processingStatus: "Processado",
  },
  {
    id: "evt-request-samsung",
    time: "20:04:44",
    eventName: "request",
    manufacturer: "Samsung",
    model: "UN49MU6100",
    modelYear: "2017",
    platform: "Tizen 3.0",
    version: "2026.3.0",
    route: "VOD",
    duration: "0,033 s",
    status: "normal",
    classification: "Requisição concluída",
    technicalDetail: "GET · HTTP 200 OK",
    userEffect: "Nenhum problema explícito foi identificado nesta requisição.",
    displayedMessage: "A requisição foi concluída com sucesso",
    source: "Loader · dataset histórico",
    processingStatus: "Processado",
  },
  {
    id: "evt-screen-panasonic",
    time: "20:04:53",
    eventName: "screen_view",
    manufacturer: "Panasonic",
    model: "43D1200",
    modelYear: "não informado",
    platform: "Linux",
    version: "2026.3.0",
    route: "Ao vivo",
    duration: "2,166 s",
    status: "normal",
    classification: "Visualização de tela",
    technicalDetail: "screen_view · live",
    userEffect: "O usuário acessou uma tela de conteúdo ao vivo.",
    displayedMessage: "Nenhuma mensagem de erro foi registrada",
    source: "Loader · dataset histórico",
    processingStatus: "Processado",
  },
  {
    id: "evt-session-panasonic",
    time: "20:04:54",
    eventName: "session · start",
    manufacturer: "Panasonic",
    model: "32D1280",
    modelYear: "não informado",
    platform: "Linux",
    version: "2026.3.0",
    route: "Sessão",
    duration: "6,486 s",
    status: "normal",
    classification: "Início de sessão",
    technicalDetail: "session:start · 1280×720",
    userEffect: "Uma sessão do aplicativo foi iniciada no dispositivo.",
    displayedMessage: "Nenhuma mensagem de erro foi registrada",
    source: "Loader · dataset histórico",
    processingStatus: "Processado",
  },
  {
    id: "evt-video-tcl",
    time: "20:05:19",
    eventName: "video_view · open",
    manufacturer: "TCL",
    model: "50P65US",
    modelYear: "2018",
    platform: "Linux",
    version: "2026.3.0",
    route: "Ao vivo",
    duration: "3,756 s",
    status: "normal",
    classification: "Abertura de conteúdo",
    technicalDetail: "video_view:open · live · ads",
    userEffect: "O usuário abriu um conteúdo ao vivo.",
    displayedMessage: "Nenhuma mensagem de erro foi registrada",
    source: "Loader · dataset histórico",
    processingStatus: "Processado",
  },
  {
    id: "evt-vitals-lg",
    time: "20:06:07",
    eventName: "vitals · frozen",
    manufacturer: "LG",
    model: "49LJ5550-SC",
    modelYear: "2017",
    platform: "webOS 3.9.0",
    version: "2026.3.0",
    route: "VOD",
    duration: "0,783 s",
    status: "attention",
    classification: "Interface congelada",
    technicalDetail: "vitals:frozen",
    userEffect: "O usuário pode ter percebido travamento ou falta de resposta do aplicativo.",
    displayedMessage: "O aplicativo deixou de responder temporariamente",
    source: "Loader · dataset histórico",
    processingStatus: "Processado",
  },
];

const prioritizedEvents = [...events].sort((eventA, eventB) => {
  if (eventA.status !== eventB.status) {
    return eventA.status === "attention" ? -1 : 1;
  }

  return eventB.time.localeCompare(eventA.time);
});

export function EventMonitor() {
  const [statusFilter, setStatusFilter] = useState<"all" | "attention" | "normal">("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [selectedId, setSelectedId] = useState(prioritizedEvents[0].id);
  const eventTypes = [...new Set(events.map((event) => event.eventName.split(" · ")[0]))];
  const filteredEvents = prioritizedEvents.filter((event) => {
    const matchesStatus = statusFilter === "all" || event.status === statusFilter;
    const matchesType = typeFilter === "all" || event.eventName.startsWith(typeFilter);
    return matchesStatus && matchesType;
  });
  const selected = filteredEvents.find((event) => event.id === selectedId) ?? filteredEvents[0] ?? prioritizedEvents[0];
  const needsAttention = selected.status === "attention";
  const attentionCount = events.filter((event) => event.status === "attention").length;
  const normalizedPayload = {
    event_id: selected.id,
    event_name: selected.eventName.split(" · ")[0],
    occurred_at: `2026-07-13T${selected.time}-03:00`,
    source: "loader",
    processing_status: selected.processingStatus.toLowerCase(),
    device: {
      manufacturer: selected.manufacturer,
      model: selected.model,
      model_year: selected.modelYear,
      platform: selected.platform,
    },
    app_version: selected.version,
    route: selected.route,
    classification: selected.classification,
  };

  return (
    <section aria-label="Eventos recebidos">
      <div className="monitor-toolbar">
        <div className="event-counters">
          <strong>{events.length} processados</strong>
          <span>{attentionCount} requerem atenção</span>
          <span>Última atualização: 20:06:10</span>
        </div>
        <div className="event-filters" aria-label="Filtros de eventos">
          <div className="status-filter">
            {(["all", "attention", "normal"] as const).map((filter) => (
              <button key={filter} type="button" aria-pressed={statusFilter === filter} onClick={() => setStatusFilter(filter)}>
                {filter === "all" ? "Todos" : filter === "attention" ? "Requer atenção" : "Normais"}
              </button>
            ))}
          </div>
          <select aria-label="Filtrar por tipo de evento" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="all">Todos os tipos</option>
            {eventTypes.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </div>
      </div>

      <div className="monitor">
      <div className="events-panel">
        <div className="panel-heading">
          <div>
            <p className="section-label">Ordenados por prioridade</p>
            <h2>Últimos eventos</h2>
          </div>
          <span className="mock-badge">6 eventos simulados</span>
        </div>

        <div className="events-list">
          {filteredEvents.map((event) => (
            <button
              type="button"
              key={event.id}
              className={event.id === selected.id ? "event-row active" : "event-row"}
              onClick={() => setSelectedId(event.id)}
            >
              <span className="event-time">{event.time}</span>
              <span className="event-main">
                <strong>{event.eventName}</strong>
                <small>{event.manufacturer} · {event.model}</small>
              </span>
              <span className={event.status === "normal" ? "event-state ok" : "event-state"}>
                <span className="sr-only">Prioridade: </span>
                {event.status === "normal" ? "normal" : "atenção"}
              </span>
            </button>
          ))}
          {filteredEvents.length === 0 && <p className="empty-list">Nenhum evento corresponde aos filtros.</p>}
        </div>
      </div>

      <article className="event-detail" aria-live="polite">
        <div className="detail-header">
          <div className={needsAttention ? "status" : "status normal"}>
            <i aria-hidden="true" />
            {needsAttention ? "Possível problema identificado" : "Evento sem falha explícita"}
          </div>
          <span>13 jul. 2026 · {selected.time}</span>
        </div>

        <h2>{selected.userEffect}</h2>

        <div className="user-message">
          <span>Mensagem ou efeito observado</span>
          <blockquote>“{selected.displayedMessage}”</blockquote>
        </div>

        <div className="detail-block">
          <h3>Contexto do evento</h3>
          <div className="tags">
            <span>{selected.manufacturer}</span><span>{selected.model}</span>
            <span>ano {selected.modelYear}</span><span>{selected.platform}</span>
            <span>{selected.route}</span><span>app {selected.version}</span>
            {selected.duration && <span>duração {selected.duration}</span>}
          </div>
        </div>

        <div className="detail-grid">
          <div><span>Classificação</span><strong>{selected.classification}</strong></div>
          <div><span>Detalhe técnico</span><code>{selected.technicalDetail}</code></div>
        </div>

        <div className="operational-grid">
          <div><span>Origem</span><strong>{selected.source}</strong></div>
          <div><span>ID técnico</span><code>{selected.id}</code></div>
          <div><span>Horário de ocorrência</span><strong>13 jul. 2026 · {selected.time}</strong></div>
        </div>

        {needsAttention && (
          <div className="analysis-notice">
            <div>
              <span>Status da análise</span>
              <strong>Evento individual — aguardando correlação</strong>
            </div>
          </div>
        )}

        <details className="payload-details">
          <summary>Ver payload normalizado</summary>
          <pre>{JSON.stringify(normalizedPayload, null, 2)}</pre>
        </details>
      </article>
      </div>
    </section>
  );
}
