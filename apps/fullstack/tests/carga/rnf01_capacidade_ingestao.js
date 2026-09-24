/**
 * RNF01 — capacidade da API de ingestão.
 *
 * Mede exatamente 1.000 req/min e, em seguida, o cenário solicitado de
 * 10.000 eventos/min. A persistência assíncrona precisa ser comprovada
 * separadamente no PostgreSQL usando o K6_TEST_ID.
 */

import http from "k6/http";
import { check } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import {
  gerarEvento,
  headersIngestao,
  INGEST_ENDPOINT,
  numero,
  taxaSucesso,
  TEST_ID,
  validarConfiguracao,
} from "./helpers.js";

const falhasIngestao = new Rate("falhas_ingestao");
const latenciaIngestao = new Trend("latencia_ingestao_ms", true);
const eventosAceitos = new Counter("eventos_aceitos");
const eventosRejeitados = new Counter("eventos_rejeitados");

export const options = {
  discardResponseBodies: true,
  scenarios: {
    aquecimento: {
      executor: "constant-arrival-rate",
      rate: 300,
      timeUnit: "1m",
      duration: "30s",
      preAllocatedVUs: 10,
      maxVUs: 30,
      exec: "enviarEvento",
      tags: { fase: "aquecimento" },
    },
    carga_nominal: {
      executor: "constant-arrival-rate",
      rate: 1000,
      timeUnit: "1m",
      duration: "1m",
      preAllocatedVUs: 30,
      maxVUs: 100,
      exec: "enviarEvento",
      startTime: "40s",
      tags: { fase: "carga_nominal" },
    },
    pico_10k: {
      executor: "constant-arrival-rate",
      rate: 10000,
      timeUnit: "1m",
      duration: "1m",
      preAllocatedVUs: 150,
      maxVUs: 500,
      exec: "enviarEvento",
      startTime: "2m",
      tags: { fase: "pico_10k" },
    },
    recuperacao: {
      executor: "constant-arrival-rate",
      rate: 1000,
      timeUnit: "1m",
      duration: "1m",
      preAllocatedVUs: 30,
      maxVUs: 100,
      exec: "enviarEvento",
      startTime: "3m20s",
      tags: { fase: "recuperacao" },
    },
  },
  thresholds: {
    "eventos_aceitos{scenario:carga_nominal}": ["count>=1000"],
    "eventos_rejeitados{scenario:carga_nominal}": ["count==0"],
    "falhas_ingestao{scenario:carga_nominal}": ["rate<0.01"],
    "latencia_ingestao_ms{scenario:carga_nominal}": ["p(95)<2000"],
    "dropped_iterations{scenario:carga_nominal}": ["count==0"],
    "falhas_ingestao{scenario:pico_10k}": ["rate<0.05"],
    "eventos_aceitos{scenario:pico_10k}": ["count>=10000"],
    "eventos_rejeitados{scenario:pico_10k}": ["count==0"],
    "latencia_ingestao_ms{scenario:pico_10k}": ["p(95)<5000"],
    "dropped_iterations{scenario:pico_10k}": ["count==0"],
    "falhas_ingestao{scenario:recuperacao}": ["rate<0.01"],
    "eventos_aceitos{scenario:recuperacao}": ["count>=1000"],
    "eventos_rejeitados{scenario:recuperacao}": ["count==0"],
    "latencia_ingestao_ms{scenario:recuperacao}": ["p(95)<2000"],
    "dropped_iterations{scenario:recuperacao}": ["count==0"],
  },
};

export function setup() {
  validarConfiguracao({ ingestao: true });
  return { testId: TEST_ID };
}

export function enviarEvento() {
  const resposta = http.post(
    INGEST_ENDPOINT,
    JSON.stringify(gerarEvento()),
    {
      headers: headersIngestao(),
      timeout: "10s",
      tags: { name: "POST /v1/events" },
    },
  );

  const sucesso = resposta.status >= 200 && resposta.status < 300;
  falhasIngestao.add(!sucesso);
  latenciaIngestao.add(resposta.timings.duration);
  if (sucesso) eventosAceitos.add(1);
  else eventosRejeitados.add(1);

  check(resposta, {
    "ingestão respondeu 2xx": () => sucesso,
    "ingestão respondeu em até 5s": (r) => r.timings.duration <= 5000,
  });
}

function submetricas(metricas, cenario) {
  return {
    aceitos: numero(metricas[`eventos_aceitos{scenario:${cenario}}`], "count"),
    rejeitados: numero(metricas[`eventos_rejeitados{scenario:${cenario}}`], "count"),
    sucesso_pct: taxaSucesso(metricas[`falhas_ingestao{scenario:${cenario}}`]).toFixed(2),
    p95_ms: numero(metricas[`latencia_ingestao_ms{scenario:${cenario}}`], "p(95)").toFixed(1),
    iteracoes_descartadas: numero(metricas[`dropped_iterations{scenario:${cenario}}`], "count"),
  };
}

export function handleSummary(data) {
  const nominal = submetricas(data.metrics, "carga_nominal");
  const pico = submetricas(data.metrics, "pico_10k");
  const recuperacao = submetricas(data.metrics, "recuperacao");
  const resumo = {
    requisito: "RNF01",
    test_id: TEST_ID,
    alvo: "API de ingestão AWS",
    configuracao: {
      nominal: "1.000 eventos/min por 1 min",
      pico: "10.000 eventos/min por 1 min",
      recuperacao: "1.000 eventos/min por 1 min",
    },
    resultado: { nominal, pico_10k: pico, recuperacao },
    aprovado_http:
      nominal.aceitos >= 1000 &&
      Number(nominal.sucesso_pct) >= 99 &&
      nominal.iteracoes_descartadas === 0 &&
      pico.aceitos >= 10000 &&
      Number(pico.sucesso_pct) >= 95 &&
      pico.iteracoes_descartadas === 0 &&
      recuperacao.aceitos >= 1000 &&
      Number(recuperacao.sucesso_pct) >= 99 &&
      recuperacao.iteracoes_descartadas === 0,
    persistencia_assincrona:
      "PENDENTE até comparar eventos aceitos com bronze.event para este test_id",
  };
  const arquivo = __ENV.K6_RESULT_FILE || "resultados/rnf01_resultado.json";
  return {
    stdout: JSON.stringify(resumo, null, 2) + "\n",
    [arquivo]: JSON.stringify(resumo, null, 2),
  };
}
