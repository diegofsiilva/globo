/**
 * Carga sobre as operações do dashboard — três níveis progressivos.
 *
 * Cada iteração reproduz a abertura de uma das seis telas operacionais
 * (/agora, /timeline, /comparar, /explorar, /recorte, /hipoteses): as mesmas
 * rotas, com os mesmos parâmetros que o frontend envia, disparadas em
 * paralelo como o navegador faz. As janelas são relativas a `sim_now`, lido
 * em /api/v1/clock, porque as views de leitura respeitam o relógio virtual.
 *
 * Os três níveis rodam em sequência no mesmo processo, com pausa entre eles,
 * e cada requisição leva a tag `nivel` para que o resumo separe os números.
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.2/index.js";
import {
  headersLeitura,
  numero,
  READ_URL,
  TEST_ID,
  validarConfiguracao,
} from "./helpers.js";

const NIVEIS = [
  { nome: "1", vus: Number(__ENV.CARGA_UI_VUS_1 || 5) },
  { nome: "2", vus: Number(__ENV.CARGA_UI_VUS_2 || 25) },
  { nome: "3", vus: Number(__ENV.CARGA_UI_VUS_3 || 100) },
];
const DURACAO = __ENV.CARGA_UI_DURACAO || "2m";
const PAUSA = __ENV.CARGA_UI_PAUSA || "30s";
const TELAS = ["agora", "timeline", "comparar", "explorar", "recorte", "hipoteses"];
// Tempo entre uma tela e a próxima. É o que separa "usuário" de "gerador de
// requisições": 100 VUs com 2 s de pausa são 100 pessoas navegando, não 100
// laços apertados contra a API.
const PENSAR_S = Number(__ENV.CARGA_UI_PENSAR_S || 2);

const telaMs = new Trend("tela_ms", true);
const telasCompletas = new Rate("telas_completas");
const telasAbertas = new Counter("telas_abertas");
const falhasPorStatus = new Counter("falhas_por_status");

function segundos(duracao) {
  const m = /^(\d+)(s|m)$/.exec(duracao);
  if (!m) throw new Error(`duracao invalida: ${duracao}`);
  return Number(m[1]) * (m[2] === "m" ? 60 : 1);
}

function montarCenarios() {
  const cenarios = {};
  let inicio = 0;
  for (const nivel of NIVEIS) {
    cenarios[`nivel_${nivel.nome}`] = {
      executor: "constant-vus",
      vus: nivel.vus,
      duration: DURACAO,
      startTime: `${inicio}s`,
      gracefulStop: "20s",
      exec: "abrirTela",
      tags: { nivel: nivel.nome },
      env: { NIVEL: nivel.nome },
    };
    inicio += segundos(DURACAO) + segundos(PAUSA);
  }
  return cenarios;
}

function montarLimiares() {
  // Os limiares por tag são o que faz o k6 imprimir um bloco por nível e por
  // tela no resumo; sem eles só o agregado aparece.
  const limiares = {
    telas_completas: ["rate>0.99"],
    // Sem limiar o k6 não lista a métrica no resumo; "count>=0" nunca reprova.
    falhas_por_status: ["count>=0"],
  };
  for (const nivel of NIVEIS) {
    const n = `nivel:${nivel.nome}`;
    limiares[`http_req_failed{${n}}`] = ["rate<0.01"];
    limiares[`http_req_duration{${n}}`] = ["p(95)<3000", "p(99)<5000"];
    limiares[`http_reqs{${n}}`] = ["count>0"];
    limiares[`telas_abertas{${n}}`] = ["count>0"];
    limiares[`tela_ms{${n}}`] = ["p(95)<5000"];
    limiares[`telas_completas{${n}}`] = ["rate>0.99"];
    for (const tela of TELAS) {
      limiares[`tela_ms{${n},tela:${tela}}`] = ["p(95)<5000"];
      limiares[`http_req_duration{${n},tela:${tela}}`] = ["p(95)<3000"];
      limiares[`http_req_failed{${n},tela:${tela}}`] = ["rate<0.01"];
    }
  }
  return limiares;
}

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  scenarios: montarCenarios(),
  thresholds: montarLimiares(),
};

function iso(ms) {
  return new Date(ms).toISOString();
}

function janela(fimMs, minutos) {
  return { from: iso(fimMs - minutos * 60_000), to: iso(fimMs) };
}

export function setup() {
  validarConfiguracao({ leitura: true });
  const relogio = http.get(`${READ_URL}/api/v1/clock`, {
    headers: headersLeitura(),
    timeout: "10s",
    tags: { name: "GET /api/v1/clock", fase: "setup" },
  });
  if (relogio.status !== 200) throw new Error(`clock respondeu ${relogio.status}`);
  const simNow = relogio.json("sim_now");
  if (!simNow) throw new Error("resposta de /api/v1/clock nao contem sim_now");
  const agora = Date.parse(simNow);
  const semana = 7 * 24 * 60;
  return {
    testId: TEST_ID,
    simNow,
    h3: janela(agora, 180),
    h3SemanaAnterior: janela(agora - semana * 60_000, 180),
    dia: janela(agora, 1440),
  };
}

/** Requisições que cada tela dispara ao abrir, com os parâmetros do frontend. */
function requisicoesDaTela(tela, ctx) {
  const q = (obj) =>
    Object.entries(obj)
      .flatMap(([k, v]) => (Array.isArray(v) ? v.map((x) => [k, x]) : [[k, v]]))
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join("&");
  const facetsEscopo = `/api/v1/series/facets?${q({ field: ["source", "entity", "metric", "tem_jogo"] })}`;
  switch (tela) {
    case "agora":
      return ["/api/v1/clock", facetsEscopo, "/api/v1/signals"];
    case "timeline":
      return ["/api/v1/clock", `/api/v1/timeline?${q(ctx.h3)}`];
    case "comparar":
      return [
        "/api/v1/clock",
        `/api/v1/series/timeseries?${q({ ...ctx.h3, interval: 6, metric: "request_count" })}`,
        `/api/v1/changes?${q(ctx.h3)}`,
        `/api/v1/series/timeseries?${q({ ...ctx.h3SemanaAnterior, interval: 6, metric: "request_count" })}`,
      ];
    case "explorar":
      return [
        "/api/v1/clock",
        facetsEscopo,
        `/api/v1/series/breakdown?${q({ dimension: "metric", ...ctx.dia, limit: 100 })}`,
        `/api/v1/series/timeseries?${q({ ...ctx.dia, interval: 5 })}`,
        `/api/v1/series/breakdown?${q({ dimension: "entity", ...ctx.dia, limit: 100, source: "youbora_device" })}`,
        `/api/v1/series/breakdown?${q({ dimension: "entity", ...ctx.dia, limit: 100, source: "youbora_device", metric: "error_rate_pct" })}`,
      ];
    case "recorte":
      return [
        "/api/v1/clock",
        facetsEscopo,
        `/api/v1/series/crosstab?${q({ dimension_x: "entity", dimension_y: "hora_brt", limit: 1000, metric: ["sessions", "error_rate_pct"] })}`,
        `/api/v1/events?${q({ limit: 100, event_name: "error" })}`,
      ];
    case "hipoteses":
      return ["/api/v1/clock", `/api/v1/hypotheses?${q(ctx.h3)}`];
    default:
      throw new Error(`tela desconhecida: ${tela}`);
  }
}

export function abrirTela(ctx) {
  const nivel = __ENV.NIVEL;
  const tela = TELAS[__ITER % TELAS.length];
  const pedidos = requisicoesDaTela(tela, ctx).map((caminho) => [
    "GET",
    `${READ_URL}${caminho}`,
    null,
    {
      headers: headersLeitura(),
      timeout: "30s",
      tags: { name: `GET ${caminho.split("?")[0]}`, tela, nivel },
    },
  ]);

  const inicio = Date.now();
  const respostas = http.batch(pedidos);
  const duracao = Date.now() - inicio;

  const todasOk = respostas.every((r) => r.status === 200);
  respostas.forEach((r, i) => {
    if (r.status === 200) return;
    const status = String(r.status);
    falhasPorStatus.add(1, { status, tela, nivel });
    // Só o caminho e o status: nem host nem cabeçalho entram no log.
    console.warn(`falha nivel=${nivel} tela=${tela} status=${status} rota=${pedidos[i][1].replace(READ_URL, "").split("?")[0]} error=${r.error || ""}`);
  });
  telaMs.add(duracao, { tela, nivel });
  telasCompletas.add(todasOk, { tela, nivel });
  telasAbertas.add(1, { tela, nivel });
  check(respostas, {
    [`${tela}: todas as rotas 200`]: () => todasOk,
    [`${tela}: aberta em <= 5 s`]: () => duracao <= 5000,
  });

  sleep(PENSAR_S);
}

function resumirNivel(data, nivel) {
  const n = `nivel:${nivel.nome}`;
  const dur = data.metrics[`http_req_duration{${n}}`];
  const falhas = data.metrics[`http_req_failed{${n}}`];
  const telas = {};
  for (const tela of TELAS) {
    const t = data.metrics[`tela_ms{${n},tela:${tela}}`];
    const d = data.metrics[`http_req_duration{${n},tela:${tela}}`];
    const f = data.metrics[`http_req_failed{${n},tela:${tela}}`];
    telas[tela] = {
      tela_p50_ms: numero(t, "med").toFixed(0),
      tela_p95_ms: numero(t, "p(95)").toFixed(0),
      tela_max_ms: numero(t, "max").toFixed(0),
      req_p95_ms: numero(d, "p(95)").toFixed(0),
      erros_pct: (numero(f, "rate") * 100).toFixed(2),
    };
  }
  return {
    usuarios: nivel.vus,
    duracao: DURACAO,
    requisicoes: numero(data.metrics[`http_reqs{${n}}`], "count"),
    telas_abertas: numero(data.metrics[`telas_abertas{${n}}`], "count"),
    erros_pct: (numero(falhas, "rate") * 100).toFixed(2),
    p50_ms: numero(dur, "med").toFixed(0),
    p95_ms: numero(dur, "p(95)").toFixed(0),
    p99_ms: numero(dur, "p(99)").toFixed(0),
    max_ms: numero(dur, "max").toFixed(0),
    tela_p95_ms: numero(data.metrics[`tela_ms{${n}}`], "p(95)").toFixed(0),
    telas_completas_pct: (numero(data.metrics[`telas_completas{${n}}`], "rate") * 100).toFixed(2),
    telas,
  };
}

export function handleSummary(data) {
  const niveis = {};
  for (const nivel of NIVEIS) niveis[`nivel_${nivel.nome}`] = resumirNivel(data, nivel);
  const resumo = {
    requisito: "carga-ui",
    test_id: TEST_ID,
    meta: "erros < 1%, p95 < 3 s e p99 < 5 s por requisicao; tela aberta em < 5 s no p95",
    pensar_s: PENSAR_S,
    total_requisicoes: numero(data.metrics.http_reqs, "count"),
    niveis,
    aprovado: Object.values(data.metrics).every((m) =>
      !m.thresholds || Object.values(m.thresholds).every((t) => t.ok),
    ),
  };
  const arquivo = __ENV.K6_RESULT_FILE || "resultados/carga_ui_resultado.json";
  return {
    stdout: textSummary(data, { indent: " ", enableColors: false }) + "\n" + JSON.stringify(resumo, null, 2) + "\n",
    [arquivo]: JSON.stringify(resumo, null, 2),
  };
}
