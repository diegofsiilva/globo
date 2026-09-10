/**
 * RNF03 — comparação de capacidade antes e depois de escalar recursos.
 *
 * Execute o mesmo arquivo em duas fases:
 *   RNF03_FASE=baseline RNF03_RATE_PER_MIN=1000
 *   RNF03_FASE=escalado  RNF03_RATE_PER_MIN=2000 (ou 10000)
 *
 * Uma rampa de tráfego isolada não prova escalabilidade; RNF03_RECURSOS
 * registra a mudança de infraestrutura.
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

const FASE = __ENV.RNF03_FASE || "";
const TAXA_POR_MINUTO = Number.parseInt(__ENV.RNF03_RATE_PER_MIN || "0", 10);
const RECURSOS = __ENV.RNF03_RECURSOS || "";
const falhasEscala = new Rate("falhas_escala");
const latenciaEscala = new Trend("latencia_escala_ms", true);
const eventosAceitosEscala = new Counter("eventos_aceitos_escala");
const eventosRejeitadosEscala = new Counter("eventos_rejeitados_escala");

export const options = {
  discardResponseBodies: true,
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
  scenarios: {
    aquecimento: {
      executor: "constant-arrival-rate",
      rate: 300,
      timeUnit: "1m",
      duration: "20s",
      preAllocatedVUs: 10,
      maxVUs: 30,
      exec: "enviar",
      tags: { fase_medicao: "aquecimento" },
    },
    medicao: {
      executor: "constant-arrival-rate",
      rate: Math.max(TAXA_POR_MINUTO, 1),
      timeUnit: "1m",
      duration: "1m",
      preAllocatedVUs: Math.max(30, Math.ceil(TAXA_POR_MINUTO / 60)),
      maxVUs: Math.max(100, Math.ceil(TAXA_POR_MINUTO / 20)),
      exec: "enviar",
      startTime: "30s",
      tags: { fase_medicao: FASE || "nao_definida" },
    },
  },
  thresholds: {
    "eventos_aceitos_escala{scenario:medicao}": [`count>=${Math.max(TAXA_POR_MINUTO, 1)}`],
    "falhas_escala{scenario:medicao}": ["rate<0.01"],
    "latencia_escala_ms{scenario:medicao}": ["p(95)<5000"],
    "dropped_iterations{scenario:medicao}": ["count==0"],
  },
};

export function setup() {
  validarConfiguracao({ ingestao: true });
  if (!["baseline", "escalado"].includes(FASE)) {
    throw new Error("RNF03_FASE deve ser baseline ou escalado");
  }
  if (!Number.isInteger(TAXA_POR_MINUTO) || TAXA_POR_MINUTO < 1) {
    throw new Error("RNF03_RATE_PER_MIN deve ser um inteiro positivo");
  }
  if (!RECURSOS.trim()) {
    throw new Error("RNF03_RECURSOS deve descrever os recursos da fase medida");
  }
  return { testId: TEST_ID, fase: FASE };
}

export function enviar() {
  const evento = gerarEvento({
    event_name: "screen_view",
    app_target: "k6_rnf03",
    rnf03_fase: FASE,
  });
  const resposta = http.post(INGEST_ENDPOINT, JSON.stringify(evento), {
    headers: headersIngestao(),
    timeout: "10s",
    tags: { name: "POST /v1/events", fase_rnf03: FASE },
  });
  const sucesso = resposta.status >= 200 && resposta.status < 300;
  falhasEscala.add(!sucesso);
  latenciaEscala.add(resposta.timings.duration);
  if (sucesso) eventosAceitosEscala.add(1);
  else eventosRejeitadosEscala.add(1);
  check(resposta, {
    "escala: status 2xx": () => sucesso,
    "escala: resposta <= 5s": (r) => r.timings.duration <= 5000,
  });
}

export function handleSummary(data) {
  const aceitos = numero(data.metrics["eventos_aceitos_escala{scenario:medicao}"], "count");
  const rejeitados = numero(data.metrics["eventos_rejeitados_escala{scenario:medicao}"], "count");
  const descartadas = numero(data.metrics["dropped_iterations{scenario:medicao}"], "count");
  const falhas = data.metrics["falhas_escala{scenario:medicao}"];
  const latencia = data.metrics["latencia_escala_ms{scenario:medicao}"];
  const resumo = {
    requisito: "RNF03",
    test_id: TEST_ID,
    fase: FASE,
    recursos: RECURSOS,
    contrato: {
      endpoint: "POST /v1/events",
      campos_obrigatorios: ["timestamp", "event_name", "session_id", "device_id"],
      gerador: "helpers.js::gerarEvento",
    },
    alvo_eventos_por_minuto: TAXA_POR_MINUTO,
    resultado: {
      aceitos,
      rejeitados,
      sucesso_pct: taxaSucesso(falhas).toFixed(2),
      p95_ms: numero(latencia, "p(95)").toFixed(1),
      p99_ms: numero(latencia, "p(99)").toFixed(1),
      iteracoes_descartadas: descartadas,
    },
    aprovado_http:
      aceitos >= TAXA_POR_MINUTO &&
      numero(falhas, "rate", 1) < 0.01 &&
      descartadas === 0,
    observacao:
      "A conclusão RNF03 exige comparar baseline e escalado e confirmar a persistência no banco.",
  };
  const arquivo =
    __ENV.K6_RESULT_FILE || `resultados/rnf03_${FASE || "invalida"}_resultado.json`;
  return {
    stdout: JSON.stringify(resumo, null, 2) + "\n",
    [arquivo]: JSON.stringify(resumo, null, 2),
  };
}
