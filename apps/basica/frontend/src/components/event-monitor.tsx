"use client";

import { useEffect, useState } from "react";

type View = "timeline" | "recorte";
const navigation = [
  { number: "01", label: "Agora", badge: "3" }, { number: "02", label: "Explorar" },
  { number: "03", label: "Comparar" }, { number: "04", label: "Hipóteses", badge: "4" },
  { number: "05", label: "Timeline", view: "timeline" as const },
  { number: "06", label: "Recorte", view: "recorte" as const },
];

/** Dashboard navegável que reproduz as telas de timeline e recorte do protótipo. */
export function EventMonitor() {
  const [view, setView] = useState<View>("timeline");
  const [period, setPeriod] = useState("30 min");
  const [time, setTime] = useState("20:11:04");
  useEffect(() => { const update = () => setTime(new Date().toLocaleTimeString("pt-BR")); update(); const timer = window.setInterval(update, 1_000); return () => window.clearInterval(timer); }, []);
  return <div className="monitor">
    <div className="live-controls"><span className="live-status"><i />Ao vivo · {time}</span><div className="periods" aria-label="Intervalo de atualização">{["15 min", "30 min", "3 h", "24 h"].map(item => <button key={item} aria-pressed={period === item} onClick={() => setPeriod(item)}>{item}</button>)}</div></div>
    <ScopeBar />
    <div className="workspace"><nav className="primary-nav" aria-label="Navegação principal">{navigation.map(item => <button key={item.number} className={item.view === view ? "active" : ""} onClick={() => item.view && setView(item.view)} disabled={!item.view}><span>{item.number}</span><strong>{item.label}</strong>{item.badge && <b>{item.badge}</b>}</button>)}</nav><main className="screen-content">{view === "timeline" ? <TimelineScreen /> : <CutScreen />}</main></div>
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
