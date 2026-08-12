"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchEvents, type ApiEvent } from "@/lib/events-api";

type DisplayEvent = {
  id: string; time: string; occurredAt: string; eventName: string;
  manufacturer: string; model: string; modelYear: string; platform: string;
  version: string; route: string; duration?: string;
  status: "normal" | "attention"; classification: string;
  technicalDetail: string; userEffect: string; displayedMessage: string;
  source: string; processingStatus: "Processado";
};

export function EventMonitor() {
  const [statusFilter, setStatusFilter] = useState<"all" | "attention" | "normal">("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [periodFilter, setPeriodFilter] = useState<"5" | "15" | "60" | "all">("15");
  const [platformFilter, setPlatformFilter] = useState("all");
  const [manufacturerFilter, setManufacturerFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const period = getPeriod(periodFilter);
  const eventsQuery = useQuery({
    queryKey: ["events", typeFilter, platformFilter, manufacturerFilter, periodFilter],
    queryFn: ({ signal }) => fetchEvents({
      eventName: typeFilter === "all" ? undefined : typeFilter,
      platform: platformFilter === "all" ? undefined : platformFilter,
      manufacturer: manufacturerFilter === "all" ? undefined : manufacturerFilter,
      ...period,
    }, signal),
  });
  const liveEvents = eventsQuery.data?.items.map(mapApiEvent) ?? [];
  const orderedEvents = [...liveEvents].sort((a, b) => a.status === b.status ? b.time.localeCompare(a.time) : a.status === "attention" ? -1 : 1);
  const eventTypes = [...new Set(liveEvents.map((event) => event.eventName.split(" · ")[0]))];
  const platforms = [...new Set(liveEvents.map((event) => event.platform))].sort();
  const manufacturers = [...new Set(liveEvents.map((event) => event.manufacturer))].sort();
  const filteredEvents = orderedEvents.filter((event) => {
    const matchesStatus = statusFilter === "all" || event.status === statusFilter;
    const matchesType = typeFilter === "all" || event.eventName.startsWith(typeFilter);
    const matchesPlatform = platformFilter === "all" || event.platform === platformFilter;
    const matchesManufacturer = manufacturerFilter === "all" || event.manufacturer === manufacturerFilter;
    const searchableContent = [event.id, event.eventName, event.manufacturer, event.model, event.modelYear, event.platform, event.version, event.route, event.classification, event.technicalDetail].join(" ").toLocaleLowerCase("pt-BR");
    const matchesQuery = searchableContent.includes(query.trim().toLocaleLowerCase("pt-BR"));
    return matchesStatus && matchesType && matchesPlatform && matchesManufacturer && matchesQuery;
  });
  const selected = filteredEvents.find((event) => event.id === selectedId) ?? filteredEvents[0] ?? orderedEvents[0] ?? null;
  const needsAttention = selected?.status === "attention";
  const attentionCount = liveEvents.filter((event) => event.status === "attention").length;
  const hypothesis = selected?.eventName.startsWith("vitals")
    ? {
        primary: "Regressão de performance na versão 2026.3.0 causando congelamento no webOS 3.9",
        score: 82,
        alternatives: [[58, "Pressão de memória no modelo LG 49LJ5550-SC"], [37, "Timeout durante a retomada do conteúdo VOD"], [21, "Instabilidade temporária do sistema operacional"]] as const,
      }
    : {
        primary: "Falha no player DASH/Shaka ao iniciar conteúdo VOD em dispositivos NetRange",
        score: 87,
        alternatives: [[61, "Manifesto DASH incompatível com o player do dispositivo"], [39, "Falha de autorização ou licença durante o início do play"], [24, "Instabilidade de rede durante o carregamento inicial"]] as const,
      };
  const normalizedPayload = selected ? {
    event_id: selected.id,
    event_name: selected.eventName.split(" · ")[0],
    occurred_at: selected.occurredAt,
    source: "api",
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
  } : null;

  return (
    <section id="eventos" aria-label="Eventos recebidos">
      <div className="monitor-toolbar">
        <div className="event-counters">
          <strong>{liveEvents.length} eventos</strong>
          <span>{attentionCount} requerem atenção</span>
          <span>{eventsQuery.isFetching ? "Atualizando…" : `Última atualização: ${new Date().toLocaleTimeString("pt-BR")}`}</span>
        </div>
        <div className="event-filters" aria-label="Filtros de eventos">
          <input type="search" aria-label="Pesquisar eventos" placeholder="Buscar modelo, versão, código..." value={query} onChange={(event) => setQuery(event.target.value)} />
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
          <select aria-label="Filtrar por período" value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value as "5" | "15" | "60" | "all")}>
            <option value="5">Últimos 5 min</option><option value="15">Últimos 15 min</option><option value="60">Última hora</option><option value="all">Todo o período</option>
          </select>
          <select aria-label="Filtrar por plataforma" value={platformFilter} onChange={(event) => setPlatformFilter(event.target.value)}>
            <option value="all">Todas as plataformas</option>{platforms.map((platform) => <option key={platform} value={platform}>{platform}</option>)}
          </select>
          <select aria-label="Filtrar por fabricante" value={manufacturerFilter} onChange={(event) => setManufacturerFilter(event.target.value)}>
            <option value="all">Todos os fabricantes</option>{manufacturers.map((manufacturer) => <option key={manufacturer} value={manufacturer}>{manufacturer}</option>)}
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
          <span className="mock-badge">{eventsQuery.isError ? "API indisponível" : "API conectada"}</span>
        </div>

        <div className="events-list">
          {filteredEvents.map((event) => (
            <button
              type="button"
              key={event.id}
              className={event.id === selected?.id ? "event-row active" : "event-row"}
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
          {eventsQuery.isLoading && <p className="empty-list">Carregando eventos…</p>}
          {!eventsQuery.isLoading && filteredEvents.length === 0 && <p className="empty-list">Nenhum evento corresponde aos filtros.</p>}
          {eventsQuery.isError && <p className="api-warning">Não foi possível consultar a API. Tente novamente.</p>}
        </div>
      </div>

      {selected ? <article className="event-detail" aria-live="polite">
        <div className="detail-header">
          <div className={needsAttention ? "status" : "status normal"}>
            <i aria-hidden="true" />
            {needsAttention ? "Possível problema identificado" : "Evento sem falha explícita"}
          </div>
          <span>{new Date(selected.occurredAt).toLocaleDateString("pt-BR")} · {selected.time}</span>
        </div>

        <h2>{selected.userEffect}</h2>
        
        <div className="detail-block">
                  <h3>Contexto do evento</h3>
                  <div className="tags">
                    <span>{selected.manufacturer}</span><span>{selected.model}</span>
                    <span>ano {selected.modelYear}</span><span>{selected.platform}</span>
                    <span>{selected.route}</span><span>app {selected.version}</span>
                    {selected.duration && <span>duração {selected.duration}</span>}
                  </div>
                </div>

        {needsAttention && <HypothesisBoard hypothesis={hypothesis} event={selected} />}

        

        <details className="payload-details">
          <summary>Ver payload normalizado</summary>
          <pre>{JSON.stringify(normalizedPayload, null, 2)}</pre>
        </details>
      </article> : <article className="event-detail empty-detail" aria-live="polite"><p>Selecione filtros ou aguarde a chegada de eventos.</p></article>}
      </div>
    </section>
  );
}

function HypothesisBoard({ hypothesis, event }: { hypothesis: { primary: string; score: number; alternatives: readonly (readonly [number, string])[] }; event: DisplayEvent }) {
  return (
    <section className="hypothesis-section hypothesis-board" id="hipoteses">
      <header className="hypothesis-title"><h3>Hipóteses de causa provável</h3><span>4 geradas · simulação demonstrativa</span></header>
      <div className="hypothesis-columns">
        <div className="hypothesis-ranking">
          <HypothesisRow score={hypothesis.score} label={hypothesis.primary} index={1} selected />
          {hypothesis.alternatives.map(([score, label], index) => <HypothesisRow key={label} score={score} label={label} index={index + 2} />)}
          <div className="discarded-hypotheses"><span>Descartadas</span><p><b>12</b> Falha geral da CDN — outros dispositivos operam normalmente.</p><p><b>08</b> Indisponibilidade do conteúdo — reprodução ocorre em outras plataformas.</p></div>
        </div>
        <div className="hypothesis-explanation">
          <span className="calculation-label">Como este score foi calculado</span>
          <h4>{hypothesis.primary}</h4>
          <div className="score-summary"><strong>{hypothesis.score}</strong><span>soma ponderada de fatores simulados, normalizada de 0–100</span></div>
          <Factor label="Correspondência com o código técnico" value={94} description={`${event.technicalDetail} aponta para o mesmo subsistema da hipótese.`} />
          <Factor label="Especificidade do dispositivo" value={88} description={`O recorte coincide com ${event.manufacturer} ${event.model} e ${event.platform}.`} />
          <Factor label="Coincidência com a versão" value={79} description={`O evento foi observado no aplicativo ${event.version}.`} />
          <Factor label="Precedente simulado" value={72} description="Cenário semelhante foi usado como histórico sintético para a demonstração." />
          <div className="consulted-evidence"><span>Evidências consultadas</span><p><b>evento normalizado</b><code>{event.id}</code></p><p><b>código técnico</b><code>{event.technicalDetail}</code></p><p><b>recorte do dispositivo</b><em>{event.manufacturer} · {event.platform}</em></p></div>
        </div>
      </div>
    </section>
  );
}

function HypothesisRow({ score, label, index, selected = false }: { score: number; label: string; index: number; selected?: boolean }) {
  return <div className={`hypothesis-row${selected ? " selected-hypothesis" : ""}`}><strong>{score}</strong><div><span>Hipótese {index}{selected ? " · principal" : ""}</span><b>{label}</b><i><em style={{ width: `${score}%` }} /></i></div></div>;
}

function Factor({ label, value, description }: { label: string; value: number; description: string }) {
  return <div className="hypothesis-factor"><div><strong>{label}</strong><span>{value}/100</span></div><i><b style={{ width: `${value}%` }} /></i><p>{description}</p></div>;
}

function mapApiEvent(event: ApiEvent): DisplayEvent {
  const occurredAt = new Date(event.occurred_at);
  const action = event.action ? ` · ${event.action}` : "";
  const isAttention = event.event_name === "error" || (event.event_name === "vitals" && event.action === "frozen");
  const errorName = readAttribute(event.attributes, "error_name");
  const errorMessage = readAttribute(event.attributes, "error_message");
  const errorStack = readAttribute(event.attributes, "error_stack");

  return {
    id: event.event_id,
    occurredAt: event.occurred_at,
    time: occurredAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    eventName: `${event.event_name}${action}`,
    manufacturer: event.device_manufacturer ?? "Não informado",
    model: event.device_model ?? "Não informado",
    modelYear: String(event.device_model_year ?? "não informado"),
    platform: [event.device_os, event.device_os_version].filter((value) => value && value !== "unknown").join(" ") || "Não informada",
    version: event.app_version ?? "Não informada",
    route: event.route_path ?? "Não informada",
    duration: event.duration_ms == null ? undefined : `${(event.duration_ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 3 })} s`,
    status: isAttention ? "attention" : "normal",
    classification: errorName ?? classifyEvent(event.event_name, event.action),
    technicalDetail: errorStack ?? `${event.event_name}${action}`,
    userEffect: describeUserEffect(event.event_name, event.action),
    displayedMessage: errorMessage ?? (isAttention ? "Possível impacto identificado no evento" : "Nenhuma falha explícita foi registrada"),
    source: "API de consulta",
    processingStatus: "Processado",
  };
}

function readAttribute(attributes: Record<string, unknown>, key: string) {
  const value = attributes[key];
  return typeof value === "string" ? value : null;
}

function classifyEvent(eventName: string, action: string | null) {
  if (eventName === "error") return "Erro da aplicação";
  if (eventName === "vitals" && action === "frozen") return "Interface congelada";
  return ({ request: "Requisição", screen_view: "Visualização de tela", session: "Sessão", video_view: "Reprodução de vídeo", vitals: "Sinal de desempenho" } as Record<string, string>)[eventName] ?? "Evento de telemetria";
}

function describeUserEffect(eventName: string, action: string | null) {
  if (eventName === "error") return "O usuário encontrou um erro durante o uso do Globoplay.";
  if (eventName === "vitals" && action === "frozen") return "O usuário pode ter percebido travamento ou falta de resposta do aplicativo.";
  if (eventName === "video_view") return "O usuário acessou um conteúdo de vídeo.";
  if (eventName === "screen_view") return "O usuário acessou uma tela do aplicativo.";
  if (eventName === "session") return "Uma sessão do aplicativo foi registrada.";
  return "Nenhum problema explícito foi identificado neste evento.";
}

function getPeriod(period: "5" | "15" | "60" | "all") {
  if (period === "all") return {};
  const to = new Date();
  const from = new Date(to.getTime() - Number(period) * 60_000);
  return { from: from.toISOString(), to: to.toISOString() };
}
