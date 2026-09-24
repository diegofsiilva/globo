/**
 * Evidência de resiliência — backlog de fila e timeout de cliente.
 *
 * backlog: execute com o event-worker em desired_count=0 e confira a fila SQS
 * antes/depois; a API deve continuar aceitando eventos de forma assíncrona.
 * timeout: força 1 ms na API de leitura e depois comprova recuperação com 7 s.
 */

import http from "k6/http";
import { check } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import {
  gerarEvento,
  headersIngestao,
  headersLeitura,
  INGEST_ENDPOINT,
  numero,
  READ_URL,
  TEST_ID,
  validarConfiguracao,
} from "./helpers.js";

const CENARIO = __ENV.FALHA_CENARIO || "";
const aceitosBacklog = new Counter("aceitos_backlog");
const falhasBacklog = new Rate("falhas_backlog");
const timeoutsInduzidos = new Counter("timeouts_induzidos");
const recuperacaoFalhou = new Rate("recuperacao_timeout_falhou");
const latenciaRecuperacao = new Trend("latencia_recuperacao_timeout_ms", true);

const scenarios = CENARIO === "backlog"
  ? {
      backlog: {
        executor: "constant-arrival-rate",
        rate: 1000,
        timeUnit: "1m",
        duration: "1m",
        preAllocatedVUs: 30,
        maxVUs: 100,
        exec: "enviarComConsumidorParado",
      },
    }
  : {
      timeout_induzido: {
        executor: "shared-iterations",
        vus: 10,
        iterations: 100,
        maxDuration: "30s",
        exec: "forcarTimeout",
      },
      recuperacao_timeout: {
        executor: "per-vu-iterations",
        vus: 1,
        iterations: 5,
        maxDuration: "1m",
        startTime: "35s",
        exec: "validarRecuperacao",
      },
    };

export const options = {
  discardResponseBodies: CENARIO === "backlog",
  scenarios,
  thresholds: CENARIO === "backlog"
    ? {
        aceitos_backlog: ["count>=1000"],
        falhas_backlog: ["rate<0.01"],
        dropped_iterations: ["count==0"],
      }
    : {
        timeouts_induzidos: ["count>=1"],
        recuperacao_timeout_falhou: ["rate==0"],
        latencia_recuperacao_timeout_ms: ["p(95)<5000"],
      },
};

export function setup() {
  if (CENARIO === "backlog") validarConfiguracao({ ingestao: true });
  else if (CENARIO === "timeout") validarConfiguracao({ leitura: true });
  else throw new Error("FALHA_CENARIO deve ser backlog ou timeout");
  return { testId: TEST_ID, cenario: CENARIO };
}

export function enviarComConsumidorParado() {
  const resposta = http.post(
    INGEST_ENDPOINT,
    JSON.stringify(gerarEvento({ event_name: "screen_view", failure_test: "backlog" })),
    {
      headers: headersIngestao(),
      timeout: "10s",
      tags: { name: "POST /v1/events", falha: "backlog" },
    },
  );
  const sucesso = resposta.status >= 200 && resposta.status < 300;
  aceitosBacklog.add(sucesso ? 1 : 0);
  falhasBacklog.add(!sucesso);
  check(resposta, { "API aceita evento com consumidor parado": () => sucesso });
}

export function forcarTimeout() {
  const resposta = http.get(`${READ_URL}/api/v1/clock`, {
    headers: headersLeitura(),
    timeout: "1ms",
    tags: { name: "GET /api/v1/clock", falha: "timeout_1ms" },
  });
  const expirou = resposta.status === 0 || Boolean(resposta.error_code);
  if (expirou) timeoutsInduzidos.add(1);
  check(resposta, { "timeout de 1 ms foi detectado": () => expirou });
}

export function validarRecuperacao() {
  const resposta = http.get(`${READ_URL}/api/v1/clock`, {
    headers: headersLeitura(),
    timeout: "7s",
    tags: { name: "GET /api/v1/clock", falha: "recuperacao_timeout" },
  });
  const sucesso = resposta.status === 200;
  recuperacaoFalhou.add(!sucesso);
  latenciaRecuperacao.add(resposta.timings.duration);
  check(resposta, {
    "API recuperou após timeout do cliente": () => sucesso,
    "recuperação respondeu em até 5 s": (r) => r.timings.duration <= 5000,
  });
}

export function handleSummary(data) {
  const resumo = CENARIO === "backlog"
    ? {
        cenario: "backlog",
        test_id: TEST_ID,
        aceitos_http: numero(data.metrics.aceitos_backlog, "count"),
        falhas_pct: (numero(data.metrics.falhas_backlog, "rate", 1) * 100).toFixed(2),
        iteracoes_descartadas: numero(data.metrics.dropped_iterations, "count"),
        observacao: "A fila SQS e a drenagem são verificadas pela AWS fora do k6.",
      }
    : {
        cenario: "timeout",
        test_id: TEST_ID,
        timeouts_detectados: numero(data.metrics.timeouts_induzidos, "count"),
        recuperacao_falhas_pct: (
          numero(data.metrics.recuperacao_timeout_falhou, "rate", 1) * 100
        ).toFixed(2),
        recuperacao_p95_ms: numero(
          data.metrics.latencia_recuperacao_timeout_ms,
          "p(95)",
        ).toFixed(1),
      };
  const arquivo = __ENV.K6_RESULT_FILE || `resultados/falha_${CENARIO}_resultado.json`;
  return { stdout: `${JSON.stringify(resumo, null, 2)}\n`, [arquivo]: JSON.stringify(resumo, null, 2) };
}
