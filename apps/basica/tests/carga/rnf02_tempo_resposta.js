/**
 * RNF02 — consultas simples do dashboard em até cinco segundos.
 *
 * As rotas individuais são repetidas cinco vezes e o filtro de eventos é
 * validado semanticamente, não apenas pelo status HTTP.
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import {
  headersLeitura,
  numero,
  READ_URL,
  taxaSucesso,
  TEST_ID,
  validarConfiguracao,
} from "./helpers.js";

const latenciaConsulta = new Trend("latencia_consulta_ms", true);
const respostasLentas = new Rate("respostas_lentas");
const falhasConsulta = new Rate("falhas_consulta");
const filtrosCorretos = new Rate("filtros_corretos");
const consultasExecutadas = new Counter("consultas_executadas");

const ROTAS = [
  { path: "/health/ready", label: "health_ready" },
  { path: "/api/v1/clock", label: "clock" },
  { path: "/api/v1/sources", label: "sources" },
  { path: "/api/v1/signals", label: "signals" },
  { path: "/api/v1/series?limit=10", label: "series" },
  { path: "/api/v1/series/facets", label: "series_facets" },
  { path: "/api/v1/incidents?limit=5", label: "incidents" },
  { path: "/api/v1/events?limit=10", label: "events" },
  { path: "/api/v1/changes", label: "changes" },
  { path: "/api/v1/timeline", label: "timeline" },
  { path: "/api/v1/facets?field=event_name", label: "facets" },
];

const ROTA_FILTRADA = {
  path: "/api/v1/events?event_name=error&app_target=android_tv&limit=100",
  label: "events_error_android_tv",
};

export const options = {
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  scenarios: {
    consultas_individuais: {
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 5,
      maxDuration: "5m",
      exec: "consultarRotas",
    },
    usuarios_concorrentes: {
      executor: "constant-vus",
      vus: 10,
      duration: "2m",
      exec: "consultaConcorrente",
      startTime: "1m",
    },
    filtros_cumulativos: {
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 5,
      maxDuration: "2m",
      exec: "consultarFiltro",
      startTime: "3m20s",
    },
    carga_sustentada: {
      executor: "constant-arrival-rate",
      rate: 600,
      timeUnit: "1m",
      duration: "2m",
      preAllocatedVUs: 20,
      maxVUs: 50,
      exec: "consultaConcorrente",
      startTime: "4m",
    },
  },
  thresholds: {
    respostas_lentas: ["rate==0"],
    falhas_consulta: ["rate==0"],
    latencia_consulta_ms: ["p(95)<3000", "p(99)<5000"],
    filtros_corretos: ["rate==1"],
    "dropped_iterations{scenario:carga_sustentada}": ["count==0"],
  },
};

export function setup() {
  validarConfiguracao({ leitura: true });
  return { testId: TEST_ID };
}

function registrar(resposta, rota) {
  const sucesso = resposta.status === 200;
  const lenta = resposta.timings.duration > 5000;
  latenciaConsulta.add(resposta.timings.duration, { rota });
  respostasLentas.add(lenta, { rota });
  falhasConsulta.add(!sucesso, { rota });
  consultasExecutadas.add(1, { rota });
  return { sucesso, lenta };
}

function get(rota) {
  return http.get(`${READ_URL}${rota.path}`, {
    headers: headersLeitura(),
    timeout: "7s",
    tags: { name: `GET ${rota.path.split("?")[0]}`, rota: rota.label },
  });
}

export function consultarRotas() {
  for (const rota of ROTAS) {
    group(`rota: ${rota.label}`, () => {
      const resposta = get(rota);
      const observado = registrar(resposta, rota.label);
      check(resposta, {
        [`${rota.label}: status 200`]: () => observado.sucesso,
        [`${rota.label}: tempo <= 5s`]: () => !observado.lenta,
        [`${rota.label}: corpo presente`]: (r) => Boolean(r.body && r.body.length > 1),
      });
    });
  }
  sleep(0.2);
}

export function consultaConcorrente() {
  const rota = ROTAS[Math.floor(Math.random() * ROTAS.length)];
  const resposta = get(rota);
  const observado = registrar(resposta, rota.label);
  check(resposta, {
    "consulta concorrente: status 200": () => observado.sucesso,
    "consulta concorrente: tempo <= 5s": () => !observado.lenta,
  });
  sleep(0.2);
}

export function consultarFiltro() {
  const resposta = get(ROTA_FILTRADA);
  const observado = registrar(resposta, ROTA_FILTRADA.label);
  let semanticaValida = false;
  if (observado.sucesso) {
    try {
      const corpo = resposta.json();
      semanticaValida =
        Array.isArray(corpo.items) &&
        corpo.items.every(
          (evento) => evento.event_name === "error" && evento.app_target === "android_tv",
        );
    } catch (_) {
      semanticaValida = false;
    }
  }
  filtrosCorretos.add(semanticaValida);
  check(resposta, {
    "filtro cumulativo: status 200": () => observado.sucesso,
    "filtro cumulativo: tempo <= 5s": () => !observado.lenta,
    "filtro cumulativo: resultados correspondem aos filtros": () => semanticaValida,
  });
}

export function handleSummary(data) {
  const lentas = numero(data.metrics.respostas_lentas, "rate", 1);
  const falhas = numero(data.metrics.falhas_consulta, "rate", 1);
  const filtros = numero(data.metrics.filtros_corretos, "rate", 0);
  const duracao = data.metrics.latencia_consulta_ms;
  const resumo = {
    requisito: "RNF02",
    test_id: TEST_ID,
    meta: "100% das consultas simples em até 5 segundos",
    resultado: {
      consultas: numero(data.metrics.consultas_executadas, "count"),
      sucesso_http_pct: taxaSucesso(data.metrics.falhas_consulta).toFixed(2),
      respostas_acima_5s_pct: (lentas * 100).toFixed(2),
      filtros_corretos_pct: (filtros * 100).toFixed(2),
      p50_ms: numero(duracao, "med").toFixed(1),
      p95_ms: numero(duracao, "p(95)").toFixed(1),
      p99_ms: numero(duracao, "p(99)").toFixed(1),
      max_ms: numero(duracao, "max").toFixed(1),
    },
    aprovado: falhas === 0 && lentas === 0 && filtros === 1,
  };
  const arquivo = __ENV.K6_RESULT_FILE || "resultados/rnf02_resultado.json";
  return {
    stdout: JSON.stringify(resumo, null, 2) + "\n",
    [arquivo]: JSON.stringify(resumo, null, 2),
  };
}
