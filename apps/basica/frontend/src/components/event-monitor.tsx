"use client";

import { useEffect, useState } from "react";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchEvents, type ApiEvent } from "@/lib/events-api";
import { Sidebar } from "@/components/sidebar";

/** Dashboard navegável que reproduz as telas de timeline e recorte do protótipo. */
export function EventMonitor() {
  const [period,setPeriod]=useState<Period>("30");
  const [now,setNow]=useState<Date|null>(null);
  const [platform,setPlatform]=useState("all");
  const [manufacturer,setManufacturer]=useState("all");
  const [eventType,setEventType]=useState("all");
  const [status,setStatus]=useState<Status>("all");
  const [search,setSearch]=useState("");
  const [selectedId,setSelectedId]=useState<string|null>(null);

  useEffect(()=>{
    const restoreTimer=window.setTimeout(()=>{
      const saved=window.localStorage.getItem("event-monitor-period");
      if(isPeriod(saved))setPeriod(saved);
      setNow(new Date());
    },0);
    const timer=window.setInterval(()=>setNow(new Date()),1_000);
    return()=>{window.clearTimeout(restoreTimer);window.clearInterval(timer)};
  },[]);

  const selectPeriod=(value:Period)=>{
    setPeriod(value);
    window.localStorage.setItem("event-monitor-period",value);
  };

  // O período vai para o backend. Os demais filtros são locais para que as opções
  // continuem disponíveis e combinações como OS + versão funcionem corretamente.
  const events=useQuery({
    queryKey:["events",period],
    queryFn:({signal})=>fetchEvents(getPeriod(period),signal),
    refetchInterval:30_000,
  });
  const allEvents=useMemo(()=>events.data?.items??[],[events.data]);
  const platforms=unique(allEvents.map(platformName));
  const manufacturers=unique(allEvents.map(e=>e.device_manufacturer).filter(isString));
  const eventTypes=unique(allEvents.map(e=>e.event_name));
  const filtered=useMemo(()=>allEvents.filter(event=>{
    const haystack=[event.event_id,event.event_name,event.action,event.device_manufacturer,event.device_model,event.device_os,event.device_os_version,event.app_version,event.route_path,event.session_id].filter(Boolean).join(" ").toLocaleLowerCase("pt-BR");
    return (platform==="all"||platformName(event)===platform)
      &&(manufacturer==="all"||event.device_manufacturer===manufacturer)
      &&(eventType==="all"||event.event_name===eventType)
      &&(status==="all"||(status==="attention")===needsAttention(event))
      &&haystack.includes(search.trim().toLocaleLowerCase("pt-BR"));
  }).sort((a,b)=>Date.parse(b.occurred_at)-Date.parse(a.occurred_at)),[allEvents,platform,manufacturer,eventType,status,search]);
  const selected=filtered.find(e=>e.event_id===selectedId)??filtered[0]??null;
  const alertCount=filtered.filter(needsAttention).length;
  const clear=()=>{setPlatform("all");setManufacturer("all");setEventType("all");setStatus("all");setSearch("")};

  return <div className="dashboard-shell">
    <div className="top-controls"><div className="live"><i/>{events.isFetching?"Atualizando":"Ao vivo"} · {now?.toLocaleTimeString("pt-BR")??"--:--:--"}</div><div className="period-picker">{(["15","30","180","1440","all"] as Period[]).map(v=><button key={v} aria-pressed={period===v} onClick={()=>selectPeriod(v)}>{periodLabel(v)}</button>)}</div></div>
    <div className="scope-bar">
      <span className="scope-label">Escopo</span>
      <Filter label="plataforma" value={platform} onChange={setPlatform} options={platforms}/>
      <Filter label="fabricante" value={manufacturer} onChange={setManufacturer} options={manufacturers}/>
      <Filter label="evento" value={eventType} onChange={setEventType} options={eventTypes}/>
      <Filter label="status" value={status} onChange={v=>setStatus(v as Status)} options={["attention","normal"]} labels={{attention:"atenção",normal:"normal"}}/>
      <input className="event-search" type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder="buscar evento…" aria-label="Buscar eventos"/>
      <p>{filtered.length} de {allEvents.length} eventos · {alertCount} requerem atenção</p><button className="clear-filter" onClick={clear}>limpar</button>
    </div>
    <div className="dashboard-body">
      <Sidebar />
      <main className="analysis-area">
        <Hero event={selected} count={filtered.length}/>
        <section className="signals-section"><header><h2>Eventos coletados pela API</h2><p>ordenados do mais recente para o mais antigo</p></header>
          <div className="signal-table"><div className="signal-head"><span>evento</span><span>dispositivo / rota</span><span>horário</span><span>duração</span><span>status</span><span>aplicativo</span><span>sessão</span></div>{filtered.map(event=><EventRow key={event.event_id} event={event} selected={event.event_id===selected?.event_id} onSelect={()=>setSelectedId(event.event_id)}/>)}</div>
          {events.isLoading&&<p className="empty-state">Consultando eventos na API…</p>}
          {events.isError&&<p className="empty-state error">Não foi possível consultar a API. Tente novamente.</p>}
          {!events.isLoading&&!events.isError&&filtered.length===0&&<p className="empty-state">Nenhum evento corresponde aos filtros selecionados.</p>}
        </section>
        {selected&&<EventDetails event={selected}/>}
      </main>
    </div>
  </div>;
}

function ScopeBar() { return <section className="scope" aria-label="Escopo da análise"><span className="scope-title">Escopo</span><ScopeChip label="plataforma" value="webOS 3.x" /><ScopeChip label="fabricante" value="LG" /><ScopeChip label="região" value="Nordeste" /><ScopeChip label="app" value="2026.3.0" /><button className="add-filter">+ filtro</button><p>41.209 sessões · 3,1% do tráfego · 6 fontes cruzadas</p><button className="clear">limpar</button></section>; }
function ScopeChip({ label, value }: { label: string; value: string }) { return <button className="scope-chip"><span>{label}</span><strong>{value}</strong><i>×</i></button>; }

const timelineRows = [
  { label:"Deploy",source:"Tsuru",event:"build 2026.3.0",detail:"19:58 · globoplay-tv",kind:"deploy",start:57,width:1.4 },
  { label:"Player QoE",source:"Youbora/NPAW",event:"falha de play 18,4%",detail:"start error · webOS 3.x",kind:"critical",start:63,width:35 },
  { label:"CDN",source:"Prometheus VTS",event:"p95 +12%",detail:"PoP Fortaleza",kind:"neutral",start:59,width:13 },
  { label:"Backend",source:"NewRelic APM",event:"autoscale +4 pods",detail:"apdex estável",kind:"neutral",start:61,width:8 },
  { label:"Identidade",source:"Apollo",event:"p99 auth 980 ms",detail:"efeito de retentativa",kind:"neutral",start:68,width:11 },
  { label:"Incidentes",source:"ServiceNow",event:"nenhum chamado",detail:"detecção 7 min antes",kind:"empty",start:91,width:0 },
];
const chronology = [
  ["19:58","TSURU","Deploy do build 2026.3.0 para a superfície TV. Rollout progressivo, 100% em 4 min."],
  ["20:00","NEWRELIC","Autoscale sobe 4 pods no backend de playback. Apdex permanece em 0,94."],
  ["20:02","PROMETHEUS","p95 na borda do PoP Fortaleza sobe de 368 ms para 412 ms."],
  ["20:04","YOUBORA","Primeira falha de início de play em LG webOS 3.x no Nordeste. dash_shaka_playback:6_6002."],
  ["20:06","APOLLO","p99 de Authorize sobe para 980 ms — compatível com retentativa do player."],
  ["20:07","AGENTE","Recorte fechado e hipótese 1 emitida com score 87. Nenhum chamado aberto até o momento."],
];

function TimelineScreen() { return <section className="timeline-screen">
  <header className="screen-heading"><h1>Timeline única do incidente</h1><p>Seis fontes em silos, um único eixo de tempo. Janela de correlação destacada.</p></header>
  <div className="timeline-chart"><div className="time-axis"><span>19:30</span><span>19:45</span><span>20:00</span><span>20:15</span><span>20:30</span></div><div className="correlation-band" />{timelineRows.map(row => <div className="timeline-row" key={row.label}><div className="source-label"><strong>{row.label}</strong><span>{row.source}</span></div><div className="track"><div className={`timeline-event ${row.kind}`} style={{left:`${row.start}%`,width:row.width?`${row.width}%`:"auto"}}><strong>{row.event}</strong><span>{row.detail}</span>{row.width > 0 && <i />}</div></div></div>)}</div>
  <div className="timeline-lower"><section className="chronology"><h2>Cronologia reconstruída</h2>{chronology.map(([hour,source,copy],index) => <div className="chronology-row" key={hour}><time className={index===0||index===3||index===5?"accent":""}>{hour}</time><b>{source}</b><p>{copy}</p></div>)}</section><aside className="correlation-card"><small>Janela de correlação</small><h2>20:00 → 20:11</h2><p>Intervalo em que o agente encontrou coincidência entre deploy, queda de QoE e ausência de sinal na CDN.</p><hr/><MetricLine label="Fontes com desvio" value="3 de 13"/><MetricLine label="Eventos correlacionados" value="412.9 k"/><MetricLine label="Detecção antes do 1º chamado" value="7 min"/><MetricLine label="Hipótese líder" value="87 / 100"/></aside></div>
  </section>; }
function MetricLine({label,value}:{label:string;value:string}) { return <div className="metric-line"><span>{label}</span><strong>{value}</strong></div>; }

const heatmap = [
  ["LG webOS 3.x","4,1%","31,2%","3,4%","2,9%","2,6%"], ["LG webOS 4+","1,4%","2,1%","1,2%","1,1%","1,0%"],
  ["Samsung Tizen","1,6%","2,0%","1,3%","1,1%","1,1%"], ["Philco NetRange","2,2%","3,0%","1,8%","1,5%","1,4%"],
  ["Android TV","1,8%","2,4%","1,5%","1,4%","1,3%"], ["iOS / tvOS","0,9%","1,1%","0,8%","0,7%","0,7%"],
];
const samples = [
  ["20:04:11","49LJ5550-SC","WebOS 3.9.0","error","dash_shaka_playback:6_6002"], ["20:04:44","43LJ5500","WebOS 3.8.0","video_view","start timeout · live"],
  ["20:05:19","32LJ600B","WebOS 3.4.0","error","media_source_not_supported"], ["20:05:52","49LJ5550-SC","WebOS 3.9.0","vitals","frozen · 0,78 s"],
  ["20:06:07","43LJ5500","WebOS 3.8.0","error","dash_shaka_playback:6_6002"], ["20:06:41","55UJ6300","WebOS 3.8.0","video_view","start timeout · live"],
];

function CutScreen() { return <section className="cut-screen">
  <header className="cut-heading"><p>Recorte afetado · definição explícita</p><h1>LG · webOS 3.x · Nordeste · app 2026.3.0 · rota live</h1><div className="cut-metrics"><CutMetric value="41.209" label="sessões"/><CutMetric value="3,1%" label="do tráfego"/><CutMetric value="94%" label="dos erros da janela"/><CutMetric value="9" label="UFs"/></div></header>
  <div className="cut-grid"><div><h2 className="section-label">Taxa de erro por família de dispositivo × região</h2><div className="heatmap"><div/><b>Norte</b><b>Nordeste</b><b>C.-Oeste</b><b>Sudeste</b><b>Sul</b>{heatmap.flatMap((row,rowIndex) => [<strong key={`${row[0]}-label`}>{row[0]}</strong>,...row.slice(1).map((cell,cellIndex)=><span key={`${row[0]}-${cellIndex}`} className={rowIndex===0&&cellIndex===1?"hottest":rowIndex===0?"hot":"warm"}>{cell}</span>)])}</div></div><aside className="adjustments"><h2>Ajustar o recorte</h2><p>O agente mede o efeito de cada ajuste sobre a especificidade do sinal antes de você clicar.</p><Adjustment title="Restringir a ISP – Oi Fibra" result="especificidade +12 · cobertura −38%" critical/><Adjustment title="Expandir para webOS 4.x" result="especificidade −41 · dilui o sinal"/><Adjustment title="Restringir a rota – live" result="especificidade +6 · cobertura −9%" critical/><Adjustment title="Remover recorte de região" result="especificidade −23 · cobertura +64%"/></aside></div>
  <section className="sample-table"><h2 className="section-label">Amostra de sessões no recorte</h2><div className="sample-head"><span>Hora</span><span>Modelo</span><span>SO</span><span>Evento</span><span>Erro</span></div>{samples.map(row=><div className="sample-row" key={row.join("-")}>{row.map((cell,index)=><span key={index} className={index===4?"sample-error":""}>{cell}</span>)}</div>)}</section>
  </section>; }
function CutMetric({value,label}:{value:string;label:string}) { return <div><strong>{value}</strong><span>{label}</span></div>; }
function Adjustment({title,result,critical=false}:{title:string;result:string;critical?:boolean}) { return <button className="adjustment"><strong>{title}</strong><span className={critical?"critical":""}>{result}</span></button>; }
