import React, { useEffect, useState } from "react"
import "./pagina.css"

export default function Pag4() {
    const [hora, setHora] = useState(new Date());

    const [selecionado, setSelecionado] = useState(0);

    const [menuSelecionado, setMenuSelecionado] = useState("Agora");

    const [hipotese, setHipotese] = useState(87);
    
    useEffect(() => {
        const intervalo = setInterval(() => {
            setHora(new Date());
        }, 1000);
        return () => clearInterval(intervalo);
    }, [])

    return(
        <div>
            <header className = "cabecalho">
                <div className = "cabecalhoEsquerda">
                    <div className = "quadrado"></div>
                    <h2>Monitoração Agêntica</h2>
                    <p>Globoplay</p>
                </div>

                <div className = "aoVivo">
                    <div className = "quadrado"></div>
                    <p className = "texto-vermelho">Ao Vivo</p>
                    <div className = "texto-vermelho">{hora.toLocaleTimeString("pt-BR")}</div>
                    <button className = {selecionado === 15 ? "botao ativado" : "botao"} onClick = {() => setSelecionado(15)}>15 min</button>
                    <button className = {selecionado === 30 ? "botao ativado" : "botao"} onClick = {() => setSelecionado(30)}>30 min</button>
                    <button className = {selecionado === 3 ? "botao ativado" : "botao"} onClick = {() => setSelecionado(3)}>3 h</button>
                    <button className = {selecionado === 24 ? "botao ativado" : "botao"} onClick = {() => setSelecionado(24)}>24 h</button>
                </div>
            </header>

            <div className = "escopo">
                <div className = "escopoEsquerda">
                    <p>Escopo</p>
                    <input type = "search" placeholder = "plataforma"></input>
                    <input type = "search" placeholder = "fabricante"></input>
                    <input type = "search" placeholder = "região"></input>
                    <input type = "search" placeholder = "app"></input>
                    <button>+ filtro</button>
                </div>

                <div className = "limpar">
                    <p>41.209 sessões · 3.1% do tráfego · 6 fontes cruzadas</p>
                </div>
            </div>

            <div className = "conteudoPrincipal">
                <div className = "menu">
                    <button className = {menuSelecionado === "Agora" ? "menuBotao ativo" : "menuBotao"} onClick = {() => setMenuSelecionado("Agora")}>Agora</button>
                    <button className = {menuSelecionado === "Explorar" ? "menuBotao ativo" : "menuBotao"} onClick = {() => setMenuSelecionado("Explorar")}>Explorar</button>
                    <button className = {menuSelecionado === "Comparar" ? "menuBotao ativo" : "menuBotao"} onClick = {() => setMenuSelecionado("Comparar")}>Comparar</button>
                    <button className = {menuSelecionado === "Hipóteses" ? "menuBotao ativo" : "menuBotao"} onClick = {() => setMenuSelecionado("Hipóteses")}>Hipóteses</button>
                    <button className = {menuSelecionado === "Timeline" ? "menuBotao ativo" : "menuBotao"} onClick = {() => setMenuSelecionado("Timeline")}>Timeline</button>
                    <button className = {menuSelecionado === "Recorte" ? "menuBotao ativo" : "menuBotao"} onClick = {() => setMenuSelecionado("Recorte")}>Recorte</button>
                </div>

                <div className ="hipoteses">
                    <h2>Hipóteses de causa provável</h2>
                    <button className = {hipotese === 87 ? "hipotesesBotao selecionado" : "hipotesesBotao"} onClick = {() => setHipotese(87)}>
                        <h2 className = {hipotese === 87 ? "textoBotao selecionado" : "textoBotao"}>87</h2>
                        <div className = "colunaTexto">
                            <p>HIPÓTESE 1 · PLAYER/BUILD</p>
                            <h2>Rollout 2026.3.0 quebrou o fallback DASH➝HLS em webOS 3.x</h2>
                            <div className = "barra"></div>
                        </div>
                    </button>
                    <button className = {hipotese === 64 ? "hipotesesBotao selecionado" : "hipotesesBotao"} onClick = {() => setHipotese(64)}>
                        <h2 className = {hipotese === 64 ? "textoBotao selecionado" : "textoBotao"}>64</h2>
                        <div className = "colunaTexto">
                            <p>HIPÓTESE 2 · CDN</p>
                            <h2>Degradação de tier 2 no PoP de Fortaleza afetando segmentos live</h2>
                            <div className = "barra" style = {{background: "linear-gradient(to right, black 0%, black 30%, dimgray 30%, dimgray 60%, slategrey 60%, slategrey 80%, darkgray 80%, darkgray 100%)"}}></div>
                        </div>
                    </button>

                    <button className = {hipotese === 41 ? "hipotesesBotao selecionado" : "hipotesesBotao"} onClick = {() => setHipotese(41)}>
                        <h2 className = {hipotese === 41 ? "textoBotao selecionado" : "textoBotao"}>41</h2>
                        <div className = "colunaTexto">
                            <p>HIPÓTESE 3 · GLOBO-ID</p>
                            <h2>Saturação de autorização elevando o tempo de início de play</h2>
                            <div className = "barra" style = {{background: "linear-gradient(to right, black 0%, black 17%, dimgray 17%, dimgray 34%, slategrey 34%, slategrey 70%, darkgray 70%, darkgray 100%)"}}></div>
                        </div>
                    </button>

                    <button className = {hipotese === 23 ? "hipotesesBotao selecionado" : "hipotesesBotao"} onClick = {() => setHipotese(23)}>
                        <h2 className = {hipotese === 23 ? "textoBotao selecionado" : "textoBotao"}>23</h2>
                        <div className = "colunaTexto">
                            <p>HIPÓTESE 4 · ENCODER/ORIGEM</p>
                            <h2>Falha de empacotamento no sinal ao vivo</h2>
                            <div className = "barra" style = {{background: "linear-gradient(to right, black 0%, black 23%, dimgray 23%, dimgray 46%, slategrey 46%, slategrey 69%, darkgray 69%, darkgray 100%)"}}></div>
                        </div>

                    </button>
                    <p>Descartadas</p>
                    <div className = "linha">
                            <p>14</p>
                            <h2>DDoS/bloqueio de borda</h2>
                            <p>─ Cloud Armor sem picos de bloqueio na janela</p>
                    </div>

                    <div className = "linha">
                        <p>11</p>
                        <h2>Falha de CMS/metadados</h2>
                        <p>─ Catálogo respondendo normalmente para o mesmo conteúdo em outras plataformas</p>
                    </div>

                    <div className = "linha">
                        <p>08</p>
                        <h2>Sazonalidade de pico</h2>
                        <p>─ Volume 12% abaixo do mesmo horário na semana passada</p>
                    </div>
                </div>

                <div className = "calculado">
                    <p>COMO ESTE SCORE FOI CALCULADO</p>

                    <h3>
                        Rollout 2026.3.0 quebrou o fallback DASH➝HLS em webOS 3.x
                    </h3>

                    <div className="calculadoLinha">
                        <h1 className="texto-vermelho">87</h1>
                        <span>
                            soma ponderada de 4 fatores, normalizada em 0-100.
                            Confiança alta
                        </span>
                    </div>

                    <div className = "separar">
                        <h3>Coincidência temporal com deploy</h3>
                        <p>peso 0,32 · contribui 29,4 pts</p>
                    </div>

                    <div className = "barra" style = {{background: "linear-gradient(to right, red 0%, red 85%, gainsboro 85%, gainsboro 100%)"}}></div>

                    <p>
                        Tsuru registra deploy do build às 19:58. Desvio começa às
                        20:04 — 6 min, dentro da janela de propagação típica (4-9 min).
                    </p>

                    <div className = "separar">
                        <h3>Especifidade do recorte</h3>
                        <p>peso 0,28 · contribui 25,1 pts</p>
                    </div>

                    <div className = "barra" style = {{background: "linear-gradient(to right, red 0%, red 83%, gainsboro 83%, gainsboro 100%)"}}></div>

                    <p>94% dos erros vêm de 3,1% do tráfego. O recorte casa exatamente com a condição de fallback: webOS ≤ 3,9 sem suporte a DRM live.</p>

                    <div className = "separar">
                        <h3>Ausência de causa concorrente</h3>
                        <p>peso 0,22 · contribui 18,0 pts</p>
                    </div>

                    <div className = "barra" style = {{background: "linear-gradient(to right, red 0%, red 70%, gainsboro 70%, gainsboro 100%)"}}></div>

                    <p>CND, Globo-ID e backend sem desvio no mesmo intervalo e nas mesmas UFs. Nenhum evento de borda no Clour Armor.</p>

                    <div className = "separar">
                        <h3>Precendente histórico</h3>
                        <p>peso 0,18 · contribui 14,5 pts</p>
                    </div>

                    <div className = "barra" style = {{background: "linear-gradient(to right, red 0%, red 67%, gainsboro 67%, gainsboro 100%)"}}></div>

                    <p>ServiceNow INC0492117 (mar/2026): mesmo sintoma, mesmo recorte, causa fechada como regressão de player.</p>

                    <p>EVIDÊNCIAS CONSULTADAS</p>

                    <div className = "separar">
                        <h3>tsuru_event</h3>
                        <p>deploy globoplay-tv · 18:58:12</p>
                    </div>

                    <div className = "separar">
                        <h3>live_error_attr_hourly</h3>
                        <p>dash_shaka_playback:6_6002 · 38.774 erros</p>
                    </div>

                    <div className = "separar">
                        <h3>geo_hourly</h3>
                        <p>9 UFs · NE concentra 71%</p>
                    </div>

                    <div className = "separar">
                        <h3>incidents</h3>
                        <p>INC0492117 · similaridade 0,81</p>
                    </div>

                    <div className = "botaoDuplo">
                        <button className = "abrirTimeline">Abrir na Timeline</button>
                        <button className = "abrirTimeline" style = {{backgroundColor: "white", color: "black"}}>Ver recorte afetado</button>
                    </div>
                </div>
            </div>
        </div>
    )
}