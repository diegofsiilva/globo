"use client";

/** Dashboard interativo para consulta e inspeção de eventos de telemetria. */

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchEvents, type ApiEvent } from "@/lib/events-api";
import { Sidebar } from "@/components/sidebar";

type Period = "15" | "30" | "180" | "1440" | "all";
type Status = "all" | "attention" | "normal";

/** @returns Monitor com atualização periódica, filtros, lista e detalhes. */
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

/** Renderiza um seletor de filtro e comunica o novo valor ao callback. */
function Filter({label,value,onChange,options,labels={}}:{label:string;value:string;onChange:(v:string)=>void;options:string[];labels?:Record<string,string>}){return <label className="scope-select"><span>{label}</span><select value={value} onChange={e=>onChange(e.target.value)}><option value="all">todos</option>{options.map(o=><option key={o} value={o}>{labels[o]??o}</option>)}</select></label>}

/** Renderiza o destaque do evento selecionado e a quantidade do recorte. */
function Hero({event,count}:{event:ApiEvent|null;count:number}){
  if(!event)return <section className="incident-hero empty-hero"><p className="incident-kicker">Monitor de telemetria</p><h1>Nenhum evento no recorte</h1><p>Ajuste os filtros ou aguarde a próxima atualização.</p></section>;
  const attention=needsAttention(event);
  return <section className="incident-hero"><p className={`incident-kicker ${attention?"":"normal"}`}><i/>{attention?"Evento requer atenção":"Evento normal"}<span>{formatDate(event.occurred_at)}</span></p><h1>{event.event_name}{event.action&&<><br/>{event.action}</>}</h1><div className="incident-stats"><Metric value={String(count)} label="eventos no recorte"/><Metric value={event.device_manufacturer??"—"} label="fabricante"/><Metric value={platformName(event)} label="plataforma"/><Metric value={duration(event)} label="duração"/></div></section>
}

/** Renderiza uma métrica composta por valor e rótulo. */
function Metric({value,label}:{value:string;label:string}){return <div className="metric"><strong>{value}</strong><span>{label}</span></div>}
/** Renderiza uma linha selecionável e chama onSelect ao ser acionada. */
function EventRow({event,selected,onSelect}:{event:ApiEvent;selected:boolean;onSelect:()=>void}){const attention=needsAttention(event);return <button className={`signal-row ${selected?"selected":""}`} onClick={onSelect}><span className="signal-name"><i className={attention?"attention":""}/><b>{event.event_name}{event.action?` · ${event.action}`:""}</b></span><span>{[event.device_manufacturer,event.device_model,event.route_path].filter(Boolean).join(" · ")||"não informado"}</span><strong>{new Date(event.occurred_at).toLocaleTimeString("pt-BR")}</strong><span>{duration(event)}</span><b className={attention?"critical":"muted"}>{attention?"atenção":"normal"}</b><span>{event.app_version??"—"}</span><strong title={event.session_id}>{shorten(event.session_id)}</strong></button>}
/** Renderiza os campos e atributos completos do evento selecionado. */
function EventDetails({event}:{event:ApiEvent}){return <section className="event-details"><p>Evento selecionado</p><div><Detail label="ID" value={event.event_id}/><Detail label="Data" value={formatDate(event.occurred_at)}/><Detail label="Dispositivo" value={[event.device_manufacturer,event.device_model,event.device_model_year].filter(Boolean).join(" · ")||"não informado"}/><Detail label="Sistema" value={platformName(event)}/><Detail label="Rota" value={event.route_path??"não informada"}/><Detail label="Versão" value={event.app_version??"não informada"}/></div><details><summary>Ver atributos recebidos</summary><pre>{JSON.stringify(event.attributes,null,2)}</pre></details></section>}
/** Renderiza um campo rotulado de detalhe. */
function Detail({label,value}:{label:string;value:string}){return <span><small>{label}</small><b>{value}</b></span>}
/** Retorna se um erro ou congelamento exige atenção operacional. */
function needsAttention(e:ApiEvent){return e.event_name==="error"||(e.event_name==="vitals"&&e.action==="frozen")}
/** Retorna o nome legível da plataforma do evento. */
function platformName(e:ApiEvent){return [e.device_os,e.device_os_version].filter(v=>v&&v!=="unknown").join(" ")||"não informada"}
/** Retorna a duração formatada em milissegundos. */
function duration(e:ApiEvent){return e.duration_ms==null?"—":`${e.duration_ms.toLocaleString("pt-BR")} ms`}
/** Converte uma data ISO em data e hora no locale brasileiro. */
function formatDate(value:string){return new Date(value).toLocaleString("pt-BR",{dateStyle:"short",timeStyle:"medium"})}
/** Encurta identificadores longos preservando seu prefixo. */
function shorten(value:string){return value.length>12?`${value.slice(0,10)}…`:value}
/** Remove duplicatas e ordena valores segundo o locale brasileiro. */
function unique(values:string[]){return [...new Set(values)].sort((a,b)=>a.localeCompare(b,"pt-BR"))}
/** Refina valores opcionais para strings não vazias. */
function isString(value:string|null):value is string{return Boolean(value)}
/** Valida valores restaurados como períodos aceitos pelo monitor. */
function isPeriod(value:string|null):value is Period{return value==="15"||value==="30"||value==="180"||value==="1440"||value==="all"}
/** Retorna o rótulo compacto correspondente ao período. */
function periodLabel(p:Period){return p==="all"?"tudo":p==="180"?"3 h":p==="1440"?"24 h":`${p} min`}
// "tudo" não manda período nenhum, e aí quem decide o recorte é a janela padrão
// da API (DEFAULT_WINDOW_HOURS, 7 dias). Existe porque a telemetria chega em
// lote: sem ela, um recorte de minutos deixa a tela vazia logo depois de uma
// carga histórica, e parece falha de integração quando é só ausência de evento
// recente.
/** Retorna o intervalo ISO do período ou nenhum filtro para todo o histórico. */
function getPeriod(p:Period){if(p==="all")return{};const to=new Date();return{from:new Date(to.getTime()-Number(p)*60_000).toISOString(),to:to.toISOString()}}
